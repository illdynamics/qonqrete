/**
 * QonQrete v2 command builder (pure, unit-testable).
 */
package sh.qonqrete.intellij.util

object ShellEscape {
    @JvmStatic
    fun escape(arg: String): String {
        if (arg.isEmpty()) return "''"
        if (arg.matches(Regex("^[a-zA-Z0-9_\\-./:=]+$"))) return arg
        return "'${arg.replace("'", "'\\''")}'"
    }

    @JvmStatic
    fun toUnixPath(windowsPath: String, isWindows: Boolean): String {
        if (!isWindows) return windowsPath
        return windowsPath.replace("\\", "/")
            .replace(Regex("^([A-Za-z]):")) { "/${it.groupValues[1].lowercase()}" }
    }
}

class CommandBuilder private constructor(private val executable: String) {
    private val parts = mutableListOf<String>()

    companion object {
        @JvmStatic
        fun qq(): CommandBuilder = CommandBuilder("qq")
    }

    fun run(taskFile: String, destinationDir: String, noTui: Boolean): CommandBuilder {
        parts += "run"
        parts += ShellEscape.escape(taskFile)
        parts += ShellEscape.escape(destinationDir)
        if (noTui) parts += "--no-tui"
        return this
    }

    fun doctor(): CommandBuilder { parts += "doctor"; return this }
    fun verify(): CommandBuilder { parts += listOf("verify", "--skip-package-steps"); return this }
    fun cleanup(repoRoot: String): CommandBuilder { parts += listOf("cleanup", "--repo-root", ShellEscape.escape(repoRoot)); return this }
    fun replay(eventsFile: String): CommandBuilder { parts += listOf("replay", ShellEscape.escape(eventsFile)); return this }
    fun runs(): CommandBuilder { parts += listOf("runs", "sessions"); return this }
    fun exec(command: String): CommandBuilder { parts += "exec"; parts += command; return this }
    fun chat(): CommandBuilder { parts += "chat"; return this }

    fun build(): String = (listOf(executable) + parts).joinToString(" ")
}
