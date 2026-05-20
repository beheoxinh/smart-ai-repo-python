use tauri::{Manager, PhysicalPosition, PhysicalSize, LogicalSize, Position, Size};
use std::fs;
use std::path::PathBuf;
use serde_json::Value;
use tauri::tray::{TrayIconBuilder, MouseButton};
use tauri::menu::{Menu, MenuItem};

#[tauri::command]
fn read_nav_config() -> Result<String, String> {
    let config_path = get_config_path()?;
    fs::read_to_string(config_path).map_err(|e| e.to_string())
}

#[tauri::command]
fn write_nav_config(config_str: &str) -> Result<(), String> {
    let config_path = get_config_path()?;
    
    // Validate JSON before writing
    let _: Value = serde_json::from_str(config_str).map_err(|e| e.to_string())?;
    
    if let Some(parent) = config_path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    
    fs::write(config_path, config_str).map_err(|e| e.to_string())
}

fn get_config_path() -> Result<PathBuf, String> {
    let home_dir = dirs::home_dir().ok_or("Could not find home directory")?;
    Ok(home_dir.join(".smartAI").join("config").join("nav_config.json"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();
            
            // Set window to be always on top, frameless, and transparent
            window.set_always_on_top(true).unwrap();
            window.set_decorations(false).unwrap();
            // In tauri v2, transparency requires setting it in tauri.conf.json as well
            
            // Dock to right side of screen
            if let Some(monitor) = window.current_monitor().unwrap() {
                let screen_size = monitor.size();
                let window_size = window.outer_size().unwrap();
                
                // Position window on the right side
                let x = (screen_size.width as i32) - (window_size.width as i32);
                let y = 0; // Top
                
                window.set_position(Position::Physical(PhysicalPosition { x, y })).unwrap();
                // Set height to full screen height
                window.set_size(Size::Physical(PhysicalSize { width: window_size.width, height: screen_size.height })).unwrap();
            }

            // Setup System Tray
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>).unwrap();
            let toggle_i = MenuItem::with_id(app, "toggle", "Toggle Visibility", true, None::<&str>).unwrap();
            let menu = Menu::with_items(app, &[&toggle_i, &quit_i]).unwrap();
            
            let tray = TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        std::process::exit(0);
                    }
                    "toggle" => {
                        let window = app.get_webview_window("main").unwrap();
                        if window.is_visible().unwrap() {
                            window.hide().unwrap();
                        } else {
                            window.show().unwrap();
                            window.set_focus().unwrap();
                        }
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let tauri::tray::TrayIconEvent::Click { button, .. } = event {
                        if button == MouseButton::Left {
                            let app = tray.app_handle();
                            let window = app.get_webview_window("main").unwrap();
                            if window.is_visible().unwrap() {
                                window.hide().unwrap();
                            } else {
                                window.show().unwrap();
                                window.set_focus().unwrap();
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            read_nav_config,
            write_nav_config
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
