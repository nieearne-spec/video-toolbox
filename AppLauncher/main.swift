import AppKit
import Foundation

let PORT = 8899
let SERVICE_DIR = NSString(string: "~/.reasonix/global-workspace/douyin-web").expandingTildeInPath
let PYTHON = NSString(string: "~/.local/venv/yt-dlp/bin/python").expandingTildeInPath
let MAIN_PY = SERVICE_DIR + "/main.py"

// ── 工具函数 ──
func isPortInUse(_ port: Int) -> Bool {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
    task.arguments = ["-ti", ":\(port)"]
    let pipe = Pipe()
    task.standardOutput = pipe; task.standardError = nil
    guard (try? task.run()) != nil else { return false }
    task.waitUntilExit()
    let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    return !out.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
}

func stopService() {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
    task.arguments = ["-ti", ":\(PORT)"]
    let pipe = Pipe()
    task.standardOutput = pipe
    guard (try? task.run()) != nil else { return }
    task.waitUntilExit()
    let pids = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .components(separatedBy: "\n").filter { !$0.isEmpty } ?? []
    for pid in pids {
        let k = Process()
        k.executableURL = URL(fileURLWithPath: "/bin/kill")
        k.arguments = ["-9", pid]
        try? k.run(); k.waitUntilExit()
    }
}

func showAlert(_ msg: String, _ info: String, _ btn1: String, _ btn2: String) -> Bool {
    let a = NSAlert(); a.messageText = msg; a.informativeText = info
    a.addButton(withTitle: btn1); a.addButton(withTitle: btn2)
    return a.runModal() == .alertFirstButtonReturn
}

func showInfo(_ msg: String, _ info: String) {
    let a = NSAlert(); a.messageText = msg; a.informativeText = info
    a.addButton(withTitle: "好"); a.runModal()
}

// ── App Delegate ──
class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        DispatchQueue.main.async {
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)

            if isPortInUse(PORT) {
                let close = showAlert("🎬 视频工具箱", "服务正在运行 (http://localhost:\(PORT))\n要关闭服务吗？", "关闭服务", "取消")
                if close {
                    stopService()
                    Thread.sleep(forTimeInterval: 0.5)
                    showInfo("✅ 已关闭", "视频工具箱已停止运行")
                }
            } else {
                self.startService()
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { NSApp.terminate(nil) }
        }
    }

    func startService() {
        // 先清理旧进程
        stopService()
        Thread.sleep(forTimeInterval: 0.5)

        let task = Process()
        task.executableURL = URL(fileURLWithPath: PYTHON)
        task.arguments = [MAIN_PY]
        task.currentDirectoryURL = URL(fileURLWithPath: SERVICE_DIR)
        let pipe = Pipe()
        task.standardOutput = pipe; task.standardError = pipe
        try? task.run()

        var started = false
        for _ in 1...10 {
            Thread.sleep(forTimeInterval: 1.0)
            if isPortInUse(PORT) { started = true; break }
        }

        if started {
            NSWorkspace.shared.open(URL(string: "http://localhost:\(PORT)")!)
            showInfo("✅ 已启动", "视频工具箱已启动\nhttp://localhost:\(PORT)")
        } else {
            showInfo("❌ 启动失败", "请检查日志:\ncat /tmp/douyin-web-app.log")
        }
    }
}

let delegate = AppDelegate()
NSApp.delegate = delegate
NSApp.setActivationPolicy(.regular)
NSApp.run()
