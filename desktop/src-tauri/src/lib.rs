//! 내 컴퓨터 지킴이 — 트레이에 상주하는 데스크톱 창.
//!
//! 화면은 frontend/ 를 그대로 담는다. 상태 판정도 화면(쉬운 화면)과 같은 함수로 하고,
//! 그 결과를 `set_tray_status` 명령으로 받아 트레이 아이콘과 메뉴 첫 줄에 보여준다.
//! 판정을 여기서 다시 구현하지 않는다 — 두 곳에서 판정하면 반드시 어긋난다.
//!
//! Linux(AppIndicator)에서는 트레이 클릭 이벤트와 툴팁이 오지 않는다. 그래서 창을 여는 길은
//! 메뉴의 "창 열기"이고, 상태는 메뉴 첫 줄 글자로도 적는다.
//!
//! API 토큰은 OS 키링에 둔다(`token_get`·`token_set`·`token_clear`). 창 안 저장소(localStorage)는
//! 앱 데이터 폴더의 평문 파일이라, 같은 계정의 다른 프로그램이 그대로 읽을 수 있다.

use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::image::Image;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{TrayIcon, TrayIconBuilder};
use tauri::{AppHandle, Manager, WindowEvent, Wry};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_notification::NotificationExt;

const ICON_OK: &[u8] = include_bytes!("../icons/tray-ok.png");
const ICON_WARN: &[u8] = include_bytes!("../icons/tray-warn.png");
const ICON_CRIT: &[u8] = include_bytes!("../icons/tray-crit.png");
const ICON_UNKNOWN: &[u8] = include_bytes!("../icons/tray-unknown.png");

/// 화면이 이 시간 넘게 상태를 보내지 않으면 '모름'으로 바꾼다.
/// 화면은 15초마다 보낸다. 창이 멈추거나 죽었는데 마지막 초록불이 남아 있으면 거짓말이 된다.
const STALE_AFTER: Duration = Duration::from_secs(60);

struct Tray {
    icon: TrayIcon<Wry>,
    status_item: MenuItem<Wry>,
    last_update: Mutex<Option<Instant>>,
    shown: Mutex<String>,
}

fn icon_for(level: &str) -> &'static [u8] {
    match level {
        "ok" => ICON_OK,
        "warn" => ICON_WARN,
        "crit" => ICON_CRIT,
        _ => ICON_UNKNOWN,
    }
}

fn show(tray: &Tray, level: &str, label: &str) -> tauri::Result<()> {
    let key = format!("{level}|{label}");
    let mut shown = tray.shown.lock().unwrap();
    if *shown == key {
        return Ok(());
    }
    tray.icon.set_icon(Some(Image::from_bytes(icon_for(level))?))?;
    tray.status_item.set_text(format!("상태: {label}"))?;
    *shown = key;
    Ok(())
}

#[tauri::command]
fn set_tray_status(app: AppHandle, level: String, label: String) -> Result<(), String> {
    let tray = app.state::<Tray>();
    show(&tray, &level, &label).map_err(|e| e.to_string())?;
    *tray.last_update.lock().unwrap() = Some(Instant::now());
    Ok(())
}

const TOKEN_SERVICE: &str = "io.github.kunmyonchoi.sentinel";
const TOKEN_USER: &str = "api-token";

fn token_entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new(TOKEN_SERVICE, TOKEN_USER).map_err(|e| e.to_string())
}

// 키링 호출은 D-Bus 를 오가며 잠금 해제 창을 띄울 수도 있다. async 명령은 주 스레드 밖에서 돌아
// 그동안 창이 멈추지 않는다.
#[tauri::command]
async fn token_get() -> Result<Option<String>, String> {
    match token_entry()?.get_password() {
        Ok(token) => Ok(Some(token)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
async fn token_set(token: String) -> Result<(), String> {
    let token = token.trim();
    if token.is_empty() {
        return Err("빈 토큰은 저장하지 않는다".into());
    }
    token_entry()?.set_password(token).map_err(|e| e.to_string())
}

#[tauri::command]
async fn token_clear() -> Result<(), String> {
    match token_entry()?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

/// 긴급 알림을 OS 알림으로 띄운다. 무엇을 언제 알릴지는 화면(desktop.js)이 정한다.
#[tauri::command]
async fn notify_urgent(app: AppHandle, title: String, body: String) -> Result<(), String> {
    app.notification().builder().title(title).body(body).show().map_err(|e| e.to_string())
}

fn open_main_window(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

pub fn run() {
    tauri::Builder::default()
        // 두 번째 실행은 새 트레이를 만들지 않고 떠 있는 창을 앞으로 가져온다. 가장 먼저 등록해야 한다.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            open_main_window(app);
        }))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![set_tray_status, token_get, token_set, token_clear, notify_urgent])
        .setup(|app| {
            let open_i = MenuItem::with_id(app, "open", "창 열기", true, None::<&str>)?;
            let status_i = MenuItem::with_id(app, "status", "상태: 확인하고 있어요", false, None::<&str>)?;
            let autostart_on = app.autolaunch().is_enabled().unwrap_or(false);
            let autostart_i = CheckMenuItem::with_id(
                app, "autostart", "로그인할 때 자동으로 켜기", true, autostart_on, None::<&str>,
            )?;
            let quit_i = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[
                &status_i,
                &PredefinedMenuItem::separator(app)?,
                &open_i,
                &autostart_i,
                &PredefinedMenuItem::separator(app)?,
                &quit_i,
            ])?;

            let autostart_for_menu = autostart_i.clone();
            let icon = TrayIconBuilder::with_id("main")
                .icon(Image::from_bytes(ICON_UNKNOWN)?)
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "open" => open_main_window(app),
                    "autostart" => {
                        let al = app.autolaunch();
                        let want = !al.is_enabled().unwrap_or(false);
                        let _ = if want { al.enable() } else { al.disable() };
                        // 실제로 바뀐 상태를 체크 표시에 반영한다. 실패했는데 체크만 바뀌면 안 된다.
                        let _ = autostart_for_menu.set_checked(al.is_enabled().unwrap_or(false));
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            app.manage(Tray {
                icon,
                status_item: status_i,
                last_update: Mutex::new(None),
                shown: Mutex::new(String::new()),
            });

            // 화면이 소식을 끊으면 '모름'. 처음 켰을 때도 첫 소식이 오기 전까지는 '확인하고 있어요'다.
            let handle = app.handle().clone();
            std::thread::spawn(move || loop {
                std::thread::sleep(Duration::from_secs(10));
                let tray = handle.state::<Tray>();
                let stale = match *tray.last_update.lock().unwrap() {
                    Some(t) => t.elapsed() > STALE_AFTER,
                    None => false,
                };
                if stale {
                    let _ = show(&tray, "unknown", "화면과 연결이 끊겼어요");
                }
            });
            Ok(())
        })
        // 창을 닫아도 앱은 트레이에 남는다. 끝내려면 트레이 메뉴의 "종료".
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("내 컴퓨터 지킴이를 시작하지 못했습니다");
}

#[cfg(test)]
mod tests {
    /// 실제 OS 키링에 쓰고 읽고 지운다. 키링 서비스가 있는 데스크톱 세션에서만 돈다:
    ///   cargo test -- --ignored
    #[test]
    #[ignore]
    fn keyring_roundtrip() {
        let entry = keyring::Entry::new("io.github.kunmyonchoi.sentinel.test", "roundtrip").unwrap();
        let _ = entry.delete_credential();
        assert!(matches!(entry.get_password(), Err(keyring::Error::NoEntry)));
        entry.set_password("secret-token-123").unwrap();
        assert_eq!(entry.get_password().unwrap(), "secret-token-123");
        entry.delete_credential().unwrap();
        assert!(matches!(entry.get_password(), Err(keyring::Error::NoEntry)));
    }
}
