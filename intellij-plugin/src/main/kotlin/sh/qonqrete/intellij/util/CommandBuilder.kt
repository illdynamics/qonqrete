/**
 * QonQrete Command Builder
 * Centralized command assembly with proper shell escaping
 * 
 * All shell command construction goes through this utility to ensure:
 * - Proper escaping of all arguments
 * - Validation of user inputs
 * - Clear, auditable command assembly
 *
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.util

import sh.qonqrete.intellij.services.QonQreteRunConfig
import sh.qonqrete.intellij.services.SanitizeResult

/**
 * Centralized shell argument escaping
 * Uses single-quote escaping for bash compatibility
 */
object ShellEscape {
    
    /**
     * Escape a string for safe use as a bash argument
     * Uses single-quote wrapping with proper escape sequence for embedded quotes
     */
    @JvmStatic
    fun escape(arg: String): String {
        if (arg.isEmpty()) return "''"
        // Safe characters that don't need escaping
        if (arg.matches(Regex("^[a-zA-Z0-9_\\-./]+$"))) return arg
        // Wrap in single quotes, escape any embedded single quotes
        return "'${arg.replace("'", "'\\''")}'"
    }
    
    /**
     * Convert Windows path to Unix path for bash
     */
    @JvmStatic
    fun toUnixPath(windowsPath: String, isWindows: Boolean): String {
        if (!isWindows) return windowsPath
        return windowsPath.replace("\\", "/").replace(Regex("^([A-Za-z]):")) { 
            "/${it.groupValues[1].lowercase()}" 
        }
    }
}

/**
 * Validation utilities for QonQrete-specific inputs
 */
object QonQreteValidation {
    
    // Valid qage name pattern: qage_YYYYMMDD_HHMMSS
    private val QAGE_NAME_REGEX = Regex("^qage_\\d{8}_\\d{6}$")
    
    // Valid characters for qonstruction names
    private val VALID_NAME_CHARS = Regex("[^a-zA-Z0-9_\\-]")
    
    // Maximum qonstruction name length
    private const val MAX_NAME_LENGTH = 64
    
    /**
     * Validate a qage name matches expected format
     */
    @JvmStatic
    fun isValidQageName(name: String): Boolean {
        return name.matches(QAGE_NAME_REGEX)
    }
    
    /**
     * Validate qage name, throwing if invalid
     */
    @JvmStatic
    fun requireValidQageName(name: String): String {
        require(isValidQageName(name)) { "Invalid qage name format: $name (expected: qage_YYYYMMDD_HHMMSS)" }
        return name
    }
    
    /**
     * Sanitize a qonstruction name, replacing invalid characters with underscores
     * Returns the result with indication of whether modification occurred
     */
    @JvmStatic
    fun sanitizeQonstructionName(name: String): SanitizeResult {
        val sanitized = name.replace(VALID_NAME_CHARS, "_").take(MAX_NAME_LENGTH)
        return SanitizeResult(name, sanitized, name != sanitized)
    }
    
    /**
     * Parse qage timestamp to epoch millis
     */
    @JvmStatic
    fun parseQageTimestamp(qageName: String): Long? {
        val match = Regex("qage_(\\d{4})(\\d{2})(\\d{2})_(\\d{2})(\\d{2})(\\d{2})").find(qageName) ?: return null
        val (year, month, day, hour, minute, second) = match.destructured
        return try {
            java.time.LocalDateTime.of(year.toInt(), month.toInt(), day.toInt(), hour.toInt(), minute.toInt(), second.toInt())
                .atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()
        } catch (_: Exception) { null }
    }
    
    /**
     * Format qage timestamp for display
     */
    @JvmStatic
    fun formatQageTimestamp(qageName: String): String {
        val timestamp = parseQageTimestamp(qageName) ?: return qageName
        val date = java.util.Date(timestamp)
        return java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(date)
    }
}

/**
 * Builder for QonQrete CLI commands
 * Ensures proper command construction with centralized escaping
 */
class CommandBuilder private constructor() {
    
    private val parts = mutableListOf<String>()
    
    companion object {
        /**
         * Start building a QonQrete command
         */
        @JvmStatic
        fun qonqrete(): CommandBuilder {
            return CommandBuilder().apply {
                parts.add("./qonqrete.sh")
            }
        }
        
        /**
         * Build a full bash script with proper escaping
         */
        @JvmStatic
        fun buildBashScript(
            workingDir: String,
            command: String,
            markerPath: String,
            restoreCommand: String? = null,
            isWindows: Boolean = false
        ): String {
            val unixWorkDir = ShellEscape.toUnixPath(workingDir, isWindows)
            val unixMarkerPath = ShellEscape.toUnixPath(markerPath, isWindows)
            
            val script = StringBuilder()
            script.append("cd ${ShellEscape.escape(unixWorkDir)} && $command; _qexit=\$?")
            
            restoreCommand?.let {
                script.append("; $it")
            }
            
            script.append("; echo \$_qexit > ${ShellEscape.escape(unixMarkerPath)}")
            script.append("; echo '[QonQrete exit code: '\$_qexit']'")
            
            return script.toString()
        }
        
        /**
         * Build restore command for temp tasq flow
         */
        @JvmStatic
        fun buildRestoreCommand(
            backupPath: String,
            tasqPath: String,
            hadOriginal: Boolean,
            isWindows: Boolean = false
        ): String {
            val unixBackup = ShellEscape.toUnixPath(backupPath, isWindows)
            val unixTasq = ShellEscape.toUnixPath(tasqPath, isWindows)
            
            return if (hadOriginal) {
                "cp ${ShellEscape.escape(unixBackup)} ${ShellEscape.escape(unixTasq)} && rm -f ${ShellEscape.escape(unixBackup)}"
            } else {
                "rm -f ${ShellEscape.escape(unixTasq)}"
            }
        }
        
        /**
         * Wrap a bash script for execution via verified bash
         */
        @JvmStatic
        fun wrapForBash(bashPath: String, script: String): String {
            return "${ShellEscape.escape(bashPath)} -c ${ShellEscape.escape(script)}"
        }
    }
    
    /**
     * Add the 'init' subcommand
     */
    fun init(): CommandBuilder {
        parts.add("init")
        return this
    }
    
    /**
     * Add the 'run' subcommand with configuration
     */
    fun run(config: QonQreteRunConfig): CommandBuilder {
        parts.add("run")
        
        // Always add sensitivity and cycles
        parts.add("--briq-sensitivity")
        parts.add(config.sensitivity.toString())
        parts.add("--cyqles")
        parts.add(config.cycles.toString())
        
        // Mode (only if not default)
        if (config.mode != "program") {
            parts.add("--mode")
            parts.add(config.mode)
        }
        
        // Autonomous
        if (config.autonomous) {
            parts.add("--auto")
        }
        
        // Qonstruction name (MUST be sanitized first)
        config.qonstructionName?.let { name ->
            val sanitized = QonQreteValidation.sanitizeQonstructionName(name)
            parts.add("--qonstruction-name")
            parts.add(ShellEscape.escape(sanitized.sanitized))
        }
        
        // Sqrapyard
        if (config.useSqrapyard) {
            parts.add("--sqrapyard")
        }
        
        // Container engine
        when (config.containerEngine) {
            "docker" -> parts.add("--docker")
            "podman" -> parts.add("--podman")
            "msb" -> parts.add("--msb")
            // "auto" -> no flag needed
        }
        
        // TUI
        if (config.enableTui) {
            parts.add("--tui")
        }
        
        // Wonqrete
        if (config.enableWonqrete) {
            parts.add("--wonqrete")
        }
        
        return this
    }
    
    /**
     * Add the 'resume' subcommand
     */
    fun resume(qageName: String? = null, config: QonQreteRunConfig? = null): CommandBuilder {
        parts.add("resume")
        
        qageName?.let {
            QonQreteValidation.requireValidQageName(it)
            parts.add("--qage")
            parts.add(it)
        }
        
        config?.let { cfg ->
            if (cfg.autonomous) {
                parts.add("--auto")
            }
            cfg.qonstructionName?.let { name ->
                val sanitized = QonQreteValidation.sanitizeQonstructionName(name)
                parts.add("--qonstruction-name")
                parts.add(ShellEscape.escape(sanitized.sanitized))
            }
        }
        
        return this
    }
    
    /**
     * Add the 'clean' subcommand
     */
    fun clean(qageName: String? = null, cleanAll: Boolean = false): CommandBuilder {
        parts.add("clean")
        
        when {
            cleanAll -> parts.add("--all")
            qageName != null -> {
                QonQreteValidation.requireValidQageName(qageName)
                parts.add("--qage")
                parts.add(qageName)
            }
        }
        
        return this
    }
    
    /**
     * Build the final command string
     */
    fun build(): String {
        return parts.joinToString(" ")
    }
}
