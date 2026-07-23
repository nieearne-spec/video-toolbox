import Foundation

let PORT = 8899
let SERVICE_DIR = NSString(string: "~/.reasonix/global-workspace/douyin-web").expandingTildeInPath
let PYTHON = NSString(string: "~/.local/venv/yt-dlp/bin/python").expandingTildeInPath
let MAIN_PY = SERVICE_DIR + "/main.py"

func runCmd(_ args: [String]) -> String {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: args[0])
    task.arguments = Array(args.dropFirst())
    let pipe = Pipe()
    task.standardOutput = pipe
    try? task.run()
    task.waitUntilExit()
    return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
}

func isPortInUse() -> Bool {
    let out = runCmd(["/usr/sbin/lsof", "-ti", ":\(PORT)"])
    return !out.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
}

func stopService() {
    let pids = runCmd(["/usr/sbin/lsof", "-ti", ":\(PORT)"])
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .components(separatedBy: "\n").filter { !$0.isEmpty }
    for pid in pids {
        _ = runCmd(["/bin/kill", "-9", pid])
    }
}

func showDialog(_ msg: String, _ info: String, _ btn1: String, _ btn2: String) -> Bool {
    let safeInfo = info.replacingOccurrences(of: "\"", with: "\\\"")
    let script = "display dialog \"\(safeInfo)\" with title \"\(msg)\" buttons {\"\(btn2)\",\"\(btn1)\"}"
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    task.arguments = ["-e", script]
    try? task.run()
    task.waitUntilExit()
    return task.terminationStatus == 0
}

func showMsg(_ msg: String, _ info: String) {
    let safeInfo = info.replacingOccurrences(of: "\"", with: "\\\"")
    let script = "display dialog \"\(safeInfo)\" with title \"\(msg)\" buttons {\"好\"}"
    let _ = runCmd(["/usr/bin/osascript", "-e", script])
}

func openBrowser(_ url: String) {
    _ = runCmd(["/usr/bin/open", url])
}

// ── 主逻辑 ──
if isPortInUse() {
    let shouldClose = showDialog("🎬 视频工具箱", "服务正在运行 (http://localhost:\(PORT))\n要关闭服务吗？", "关闭服务", "取消")
    if shouldClose {
        stopService()
        Thread.sleep(forTimeInterval: 0.5)
        showMsg("✅ 已关闭", "视频工具箱已停止运行")
    }
} else {
    stopService()
    Thread.sleep(forTimeInterval: 0.5)

    let task = Process()
    task.executableURL = URL(fileURLWithPath: PYTHON)
    task.arguments = [MAIN_PY]
    task.currentDirectoryURL = URL(fileURLWithPath: SERVICE_DIR)
    try? task.run()

    var started = false
    for _ in 1...10 {
        Thread.sleep(forTimeInterval: 1.0)
        if isPortInUse() { started = true; break }
    }

    if started {
        openBrowser("http://localhost:\(PORT)")
        showMsg("✅ 已启动", "视频工具箱已启动\nhttp://localhost:\(PORT)")
    } else {
        showMsg("❌ 启动失败", "请查看日志:\ncat /tmp/douyin-web-app.log")
    }
}
