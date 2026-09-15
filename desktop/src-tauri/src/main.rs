// 릴리스 빌드에서 Windows 콘솔 창이 뜨지 않게 한다. Linux 에는 영향이 없다.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    sentinel_desktop_lib::run()
}
