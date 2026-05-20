package main

import (
    "context"
    "embed"
    "encoding/json"
    "io/fs"
    "log"
    "mime"
    "net"
    "net/http"
    "os"
    "path/filepath"
    "sort"
    "strings"
    "sync"
    "time"

    "github.com/webview/webview"
)

const (
    defaultStartURL = "https://chatgpt.com/"
)

var (
    //go:embed assets/frontend/*
    frontendFiles embed.FS

    //go:embed assets/images/*
    imageAssets embed.FS

    //go:embed assets/config/nav_config_default.json
    defaultNavConfig []byte

    appLogger = log.New(os.Stdout, "golang-ai-sidebar: ", log.LstdFlags)
)

type AppPaths struct {
    rootDir   string
    configDir string
    imagesDir string
}

type NavItem struct {
    Icon    string `json:"icon"`
    Tooltip string `json:"tooltip"`
    URL     string `json:"url"`
    Pinned  bool   `json:"pinned"`
    Order   int    `json:"order"`
}

func main() {
    paths := newAppPaths()
    if err := paths.ensureDirs(); err != nil {
        appLogger.Fatalf("can't ensure directories: %v", err)
    }

    if err := paths.syncDefaultIcons(); err != nil {
        appLogger.Printf("warning syncing icons: %v", err)
    }

    if err := ensureNavConfig(paths); err != nil {
        appLogger.Fatalf("failed to create nav config: %v", err)
    }

    address, shutdown := startServer(paths)
    defer shutdown()

    runWebview(address)
}

func newAppPaths() *AppPaths {
    home, err := os.UserHomeDir()
    if err != nil || home == "" {
        home = "."
    }

    root := filepath.Join(home, ".smartAI")
    return &AppPaths{
        rootDir:   root,
        configDir: filepath.Join(root, "config"),
        imagesDir: filepath.Join(root, "images"),
    }
}

func (p *AppPaths) ensureDirs() error {
    for _, dir := range []string{p.rootDir, p.configDir, p.imagesDir} {
        if err := os.MkdirAll(dir, 0o755); err != nil {
            return err
        }
    }
    return nil
}

func (p *AppPaths) syncDefaultIcons() error {
    entries, err := imageAssets.ReadDir("assets/images")
    if err != nil {
        return err
    }

    for _, entry := range entries {
        if entry.IsDir() {
            continue
        }

        dest := filepath.Join(p.imagesDir, entry.Name())
        if _, err := os.Stat(dest); err == nil {
            continue
        }

        data, err := imageAssets.ReadFile(filepath.Join("assets/images", entry.Name()))
        if err != nil {
            return err
        }

        if err := os.WriteFile(dest, data, 0o644); err != nil {
            return err
        }
    }
    return nil
}

func (p *AppPaths) configFilePath() string {
    return filepath.Join(p.configDir, "nav_config.json")
}

func (p *AppPaths) lastURLPath() string {
    return filepath.Join(p.configDir, "last_url.txt")
}

func ensureNavConfig(paths *AppPaths) error {
    cfg := paths.configFilePath()

    if _, err := os.Stat(cfg); err == nil {
        return nil
    }

    return os.WriteFile(cfg, defaultNavConfig, 0o644)
}

func loadNavConfig(paths *AppPaths) ([]NavItem, error) {
    data, err := os.ReadFile(paths.configFilePath())
    if err != nil {
        return nil, err
    }

    var items []NavItem
    if err := json.Unmarshal(data, &items); err != nil {
        appLogger.Printf("invalid nav config: %v", err)
        if err := os.WriteFile(paths.configFilePath(), defaultNavConfig, 0o644); err != nil {
            return nil, err
        }
        if err := json.Unmarshal(defaultNavConfig, &items); err != nil {
            return nil, err
        }
    }

    sort.SliceStable(items, func(i, j int) bool {
        return items[i].Order < items[j].Order
    })

    return items, nil
}

func saveNavConfig(paths *AppPaths, items []NavItem) error {
    sort.SliceStable(items, func(i, j int) bool {
        return items[i].Order < items[j].Order
    })

    data, err := json.MarshalIndent(items, "", "  ")
    if err != nil {
        return err
    }

    return os.WriteFile(paths.configFilePath(), data, 0o644)
}

func loadLastURL(paths *AppPaths) string {
    data, err := os.ReadFile(paths.lastURLPath())
    if err != nil {
        return ""
    }
    return strings.TrimSpace(string(data))
}

func saveLastURL(paths *AppPaths, value string) error {
    return os.WriteFile(paths.lastURLPath(), []byte(value), 0o644)
}

func startServer(paths *AppPaths) (string, func()) {
    frontend, err := fs.Sub(frontendFiles, "assets/frontend")
    if err != nil {
        appLogger.Fatalf("failed to locate frontend assets: %v", err)
    }

    mux := http.NewServeMux()
    mux.HandleFunc("/api/nav", makeNavHandler(paths))
    mux.HandleFunc("/api/last-url", makeLastURLHandler(paths))
    mux.Handle("/images/", http.StripPrefix("/images/", http.FileServer(http.Dir(paths.imagesDir))))
    mux.Handle("/", spaHandler(frontend))

    listener, err := net.Listen("tcp", "127.0.0.1:0")
    if err != nil {
        appLogger.Fatalf("failed to pick a port: %v", err)
    }

    server := &http.Server{Handler: mux}
    go func() {
        if err := server.Serve(listener); err != nil && err != http.ErrServerClosed {
            appLogger.Printf("http server stopped: %v", err)
        }
    }()

    shutdown := func() {
        ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
        defer cancel()
        if err := server.Shutdown(ctx); err != nil {
            appLogger.Printf("server shutdown error: %v", err)
        }
    }

    return "http://" + listener.Addr().String(), shutdown
}

func makeNavHandler(paths *AppPaths) http.HandlerFunc {
    var mu sync.Mutex

    return func(w http.ResponseWriter, r *http.Request) {
        switch r.Method {
        case http.MethodGet:
            items, err := loadNavConfig(paths)
            if err != nil {
                http.Error(w, "failed to load nav config", http.StatusInternalServerError)
                return
            }
            writeJSON(w, items)

        case http.MethodPost:
            mu.Lock()
            defer mu.Unlock()

            var payload NavItem
            if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
                http.Error(w, "invalid JSON", http.StatusBadRequest)
                return
            }

            payload.URL = normalizeURL(payload.URL)
            if payload.URL == "" || payload.Icon == "" {
                http.Error(w, "icon and url are required", http.StatusBadRequest)
                return
            }

            items, err := loadNavConfig(paths)
            if err != nil {
                http.Error(w, "can't open config", http.StatusInternalServerError)
                return
            }

            if payload.Order <= 0 {
                payload.Order = len(items)
            }
            items = append(items, payload)

            if err := saveNavConfig(paths, items); err != nil {
                http.Error(w, "can't save config", http.StatusInternalServerError)
                return
            }

            writeJSON(w, items)

        default:
            w.Header().Set("Allow", "GET, POST")
            http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
        }
    }
}

func makeLastURLHandler(paths *AppPaths) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        switch r.Method {
        case http.MethodGet:
            last := loadLastURL(paths)
            if last == "" {
                last = defaultStartURL
            }
            writeJSON(w, map[string]string{"url": last})

        case http.MethodPost:
            var payload struct {
                URL string `json:"url"`
            }
            if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
                http.Error(w, "invalid JSON", http.StatusBadRequest)
                return
            }
            payload.URL = normalizeURL(payload.URL)
            if payload.URL == "" {
                http.Error(w, "url is required", http.StatusBadRequest)
                return
            }
            if err := saveLastURL(paths, payload.URL); err != nil {
                http.Error(w, "failed to save url", http.StatusInternalServerError)
                return
            }
            w.WriteHeader(http.StatusNoContent)

        default:
            w.Header().Set("Allow", "GET, POST")
            http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
        }
    }
}

func writeJSON(w http.ResponseWriter, payload interface{}) {
    w.Header().Set("Content-Type", "application/json; charset=utf-8")
    _ = json.NewEncoder(w).Encode(payload)
}

func normalizeURL(value string) string {
    trimmed := strings.TrimSpace(value)
    if trimmed == "" {
        return ""
    }
    if strings.HasPrefix(trimmed, "http://") || strings.HasPrefix(trimmed, "https://") {
        return trimmed
    }
    return "https://" + trimmed
}

func spaHandler(frontend fs.FS) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        path := strings.TrimPrefix(r.URL.Path, "/")
        if path == "" {
            path = "index.html"
        }

        if _, err := fs.Stat(frontend, path); err != nil {
            path = "index.html"
        }

        file, err := frontend.Open(path)
        if err != nil {
            http.Error(w, "not found", http.StatusNotFound)
            return
        }
        defer file.Close()

        stat, err := file.Stat()
        if err != nil {
            http.Error(w, "failed to read asset", http.StatusInternalServerError)
            return
        }

        if ctype := mime.TypeByExtension(filepath.Ext(path)); ctype != "" {
            w.Header().Set("Content-Type", ctype)
        }

        http.ServeContent(w, r, path, stat.ModTime(), file)
    })
}

func runWebview(address string) {
    w := webview.New(true)
    defer w.Destroy()

    w.SetTitle("Golang AI Sidebar")
    w.SetSize(1000, 720, webview.HintNone)
    w.SetColor(0x333333)
    w.Navigate(address)
    w.Run()
}
