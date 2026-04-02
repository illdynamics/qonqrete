/**
 * QonQrete Service Tests
 * Tests for ACTUAL implementation utilities - not duplicated helpers
 *
 * v1.1.9: Tests real ShellEscape, QonQreteValidation, and CommandBuilder utilities
 *
 * @author WoNQ
 * @version 1.2.4
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.io.TempDir
import org.junit.jupiter.api.assertThrows
import sh.qonqrete.intellij.services.*
import sh.qonqrete.intellij.util.*
import java.io.File
import java.nio.file.Path

class QonQreteServiceTest {

    @TempDir
    lateinit var tempDir: Path

    // ========================================================================
    // SHELL ESCAPE TESTS - Testing ACTUAL ShellEscape utility
    // ========================================================================

    @Test
    fun `ShellEscape escape returns empty string quoted`() {
        assertEquals("''", ShellEscape.escape(""))
    }

    @Test
    fun `ShellEscape escape preserves safe strings`() {
        assertEquals("test", ShellEscape.escape("test"))
        assertEquals("my-project", ShellEscape.escape("my-project"))
        assertEquals("path/to/file", ShellEscape.escape("path/to/file"))
        assertEquals("file_name.txt", ShellEscape.escape("file_name.txt"))
        assertEquals("CamelCase123", ShellEscape.escape("CamelCase123"))
    }

    @Test
    fun `ShellEscape escape quotes strings with spaces`() {
        assertEquals("'my project'", ShellEscape.escape("my project"))
        assertEquals("'has multiple spaces'", ShellEscape.escape("has multiple spaces"))
    }

    @Test
    fun `ShellEscape escape handles embedded single quotes`() {
        assertEquals("'it'\\''s'", ShellEscape.escape("it's"))
        assertEquals("'don'\\''t'", ShellEscape.escape("don't"))
        assertEquals("'can'\\''t stop'", ShellEscape.escape("can't stop"))
    }

    @Test
    fun `ShellEscape escape quotes special characters`() {
        assertEquals("'test@build'", ShellEscape.escape("test@build"))
        assertEquals("'hello!world'", ShellEscape.escape("hello!world"))
        assertEquals("'test#var'", ShellEscape.escape("test#var"))
        assertEquals("'\$HOME'", ShellEscape.escape("\$HOME"))
    }

    @Test
    fun `ShellEscape toUnixPath converts Windows paths`() {
        assertEquals("/c/Users/test", ShellEscape.toUnixPath("C:\\Users\\test", true))
        assertEquals("/d/Projects/code", ShellEscape.toUnixPath("D:\\Projects\\code", true))
    }

    @Test
    fun `ShellEscape toUnixPath preserves Unix paths`() {
        assertEquals("/home/user/test", ShellEscape.toUnixPath("/home/user/test", false))
        assertEquals("/var/log/app.log", ShellEscape.toUnixPath("/var/log/app.log", false))
    }

    @Test
    fun `ShellEscape toUnixPath handles lowercase drive letters`() {
        assertEquals("/e/data/file", ShellEscape.toUnixPath("e:\\data\\file", true))
    }

    // ========================================================================
    // QONQRETE VALIDATION TESTS - Testing ACTUAL QonQreteValidation utility
    // ========================================================================

    @Test
    fun `QonQreteValidation isValidQageName accepts valid names`() {
        assertTrue(QonQreteValidation.isValidQageName("qage_20250313_143052"))
        assertTrue(QonQreteValidation.isValidQageName("qage_19990101_000000"))
        assertTrue(QonQreteValidation.isValidQageName("qage_20991231_235959"))
    }

    @Test
    fun `QonQreteValidation isValidQageName rejects invalid names`() {
        assertFalse(QonQreteValidation.isValidQageName("qage_invalid"))
        assertFalse(QonQreteValidation.isValidQageName("qage_2025031_143052"))  // Too few date digits
        assertFalse(QonQreteValidation.isValidQageName("qage_20250313_14305"))   // Too few time digits
        assertFalse(QonQreteValidation.isValidQageName("qage_20250313143052"))   // No underscore
        assertFalse(QonQreteValidation.isValidQageName("not_a_qage"))
        assertFalse(QonQreteValidation.isValidQageName(""))
        assertFalse(QonQreteValidation.isValidQageName("QAGE_20250313_143052"))  // Uppercase
    }

    @Test
    fun `QonQreteValidation requireValidQageName throws on invalid`() {
        val exception = assertThrows<IllegalArgumentException> {
            QonQreteValidation.requireValidQageName("invalid_qage")
        }
        assertTrue(exception.message!!.contains("Invalid qage name format"))
    }

    @Test
    fun `QonQreteValidation requireValidQageName returns valid name`() {
        val validName = "qage_20250313_143052"
        assertEquals(validName, QonQreteValidation.requireValidQageName(validName))
    }

    @Test
    fun `QonQreteValidation sanitizeQonstructionName preserves valid names`() {
        val validNames = listOf("my-project", "MyProject123", "test_build", "simple", "a", "A-B_C")
        for (name in validNames) {
            val result = QonQreteValidation.sanitizeQonstructionName(name)
            assertEquals(name, result.sanitized, "Expected '$name' to be unchanged")
            assertFalse(result.wasModified, "Expected '$name' to not be modified")
        }
    }

    @Test
    fun `QonQreteValidation sanitizeQonstructionName replaces invalid chars`() {
        val testCases = mapOf(
            "my project" to "my_project",
            "test@build" to "test_build",
            "hello!world" to "hello_world",
            "a/b/c" to "a_b_c",
            "file.name" to "file_name",
            "special#chars\$here" to "special_chars_here"
        )
        for ((input, expected) in testCases) {
            val result = QonQreteValidation.sanitizeQonstructionName(input)
            assertEquals(expected, result.sanitized, "Expected '$input' -> '$expected'")
            assertTrue(result.wasModified, "Expected '$input' to be modified")
        }
    }

    @Test
    fun `QonQreteValidation sanitizeQonstructionName truncates to 64 chars`() {
        val longName = "a".repeat(100)
        val result = QonQreteValidation.sanitizeQonstructionName(longName)
        assertEquals(64, result.sanitized.length)
        assertTrue(result.wasModified)
    }

    @Test
    fun `QonQreteValidation sanitizeQonstructionName handles empty string`() {
        val result = QonQreteValidation.sanitizeQonstructionName("")
        assertEquals("", result.sanitized)
        assertFalse(result.wasModified)
    }

    @Test
    fun `QonQreteValidation parseQageTimestamp extracts correct timestamp`() {
        val qageName = "qage_20250313_143052"
        val timestamp = QonQreteValidation.parseQageTimestamp(qageName)
        
        assertNotNull(timestamp)
        
        val calendar = java.util.Calendar.getInstance()
        calendar.timeInMillis = timestamp!!
        
        assertEquals(2025, calendar.get(java.util.Calendar.YEAR))
        assertEquals(2, calendar.get(java.util.Calendar.MONTH)) // March = 2 (0-indexed)
        assertEquals(13, calendar.get(java.util.Calendar.DAY_OF_MONTH))
        assertEquals(14, calendar.get(java.util.Calendar.HOUR_OF_DAY))
        assertEquals(30, calendar.get(java.util.Calendar.MINUTE))
        assertEquals(52, calendar.get(java.util.Calendar.SECOND))
    }

    @Test
    fun `QonQreteValidation parseQageTimestamp returns null for invalid`() {
        assertNull(QonQreteValidation.parseQageTimestamp("qage_invalid"))
        assertNull(QonQreteValidation.parseQageTimestamp(""))
        assertNull(QonQreteValidation.parseQageTimestamp("not_a_qage"))
    }

    @Test
    fun `QonQreteValidation formatQageTimestamp produces readable format`() {
        val formatted = QonQreteValidation.formatQageTimestamp("qage_20250313_143052")
        assertTrue(formatted.contains("2025"))
        assertTrue(formatted.contains("03") || formatted.contains("3"))
        assertTrue(formatted.contains("13"))
    }

    // ========================================================================
    // COMMAND BUILDER TESTS - Testing ACTUAL CommandBuilder utility
    // ========================================================================

    @Test
    fun `CommandBuilder init produces correct command`() {
        val command = CommandBuilder.qonqrete().init().build()
        assertEquals("./qonqrete.sh init", command)
    }

    @Test
    fun `CommandBuilder run with default config`() {
        val config = QonQreteRunConfig()
        val command = CommandBuilder.qonqrete().run(config).build()
        assertEquals("./qonqrete.sh run --briq-sensitivity 6 --cyqles 3", command)
    }

    @Test
    fun `CommandBuilder run with full config`() {
        val config = QonQreteRunConfig(
            sensitivity = 10,
            cycles = 5,
            mode = "security",
            autonomous = true,
            qonstructionName = "my-build",
            useSqrapyard = true,
            containerEngine = "docker",
            enableTui = true,
            enableWonqrete = true
        )
        val command = CommandBuilder.qonqrete().run(config).build()
        
        assertTrue(command.contains("--briq-sensitivity 10"))
        assertTrue(command.contains("--cyqles 5"))
        assertTrue(command.contains("--mode security"))
        assertTrue(command.contains("--auto"))
        assertTrue(command.contains("--qonstruction-name my-build"))
        assertTrue(command.contains("--sqrapyard"))
        assertTrue(command.contains("--docker"))
        assertTrue(command.contains("--tui"))
        assertTrue(command.contains("--wonqrete"))
    }

    @Test
    fun `CommandBuilder run escapes qonstruction name with spaces`() {
        val config = QonQreteRunConfig(qonstructionName = "my build")
        val command = CommandBuilder.qonqrete().run(config).build()
        // Sanitization replaces space with underscore
        assertTrue(command.contains("--qonstruction-name my_build"))
    }

    @Test
    fun `CommandBuilder resume without qage`() {
        val command = CommandBuilder.qonqrete().resume().build()
        assertEquals("./qonqrete.sh resume", command)
    }

    @Test
    fun `CommandBuilder resume with qage`() {
        val command = CommandBuilder.qonqrete().resume("qage_20250313_143052").build()
        assertEquals("./qonqrete.sh resume --qage qage_20250313_143052", command)
    }

    @Test
    fun `CommandBuilder resume with invalid qage throws`() {
        assertThrows<IllegalArgumentException> {
            CommandBuilder.qonqrete().resume("invalid_qage").build()
        }
    }

    @Test
    fun `CommandBuilder clean without args`() {
        val command = CommandBuilder.qonqrete().clean().build()
        assertEquals("./qonqrete.sh clean", command)
    }

    @Test
    fun `CommandBuilder clean with qage`() {
        val command = CommandBuilder.qonqrete().clean(qageName = "qage_20250313_143052").build()
        assertEquals("./qonqrete.sh clean --qage qage_20250313_143052", command)
    }

    @Test
    fun `CommandBuilder clean all`() {
        val command = CommandBuilder.qonqrete().clean(cleanAll = true).build()
        assertEquals("./qonqrete.sh clean --all", command)
    }

    @Test
    fun `CommandBuilder buildBashScript creates proper script`() {
        val script = CommandBuilder.buildBashScript(
            workingDir = "/home/user/project",
            command = "./qonqrete.sh run --auto",
            markerPath = "/home/user/project/worqspace/.qonqrete_run_123.marker",
            isWindows = false
        )
        
        assertTrue(script.contains("cd"))
        assertTrue(script.contains("./qonqrete.sh run --auto"))
        assertTrue(script.contains("_qexit=\$?"))
        assertTrue(script.contains("echo \$_qexit >"))
        assertTrue(script.contains(".marker"))
    }

    @Test
    fun `CommandBuilder buildRestoreCommand with original`() {
        val cmd = CommandBuilder.buildRestoreCommand(
            backupPath = "/home/user/backup",
            tasqPath = "/home/user/tasq.md",
            hadOriginal = true,
            isWindows = false
        )
        
        assertTrue(cmd.contains("cp"))
        assertTrue(cmd.contains("rm -f"))
    }

    @Test
    fun `CommandBuilder buildRestoreCommand without original`() {
        val cmd = CommandBuilder.buildRestoreCommand(
            backupPath = "/home/user/backup",
            tasqPath = "/home/user/tasq.md",
            hadOriginal = false,
            isWindows = false
        )
        
        assertTrue(cmd.startsWith("rm -f"))
        assertFalse(cmd.contains("cp"))
    }

    @Test
    fun `CommandBuilder wrapForBash creates proper wrapping`() {
        val wrapped = CommandBuilder.wrapForBash("/bin/bash", "echo hello")
        assertTrue(wrapped.startsWith("/bin/bash"))
        assertTrue(wrapped.contains("-c"))
    }

    // ========================================================================
    // QONQRETE RUN CONFIG TESTS
    // ========================================================================

    @Test
    fun `QonQreteRunConfig defaults are correct`() {
        val config = QonQreteRunConfig()
        assertEquals(6, config.sensitivity)
        assertEquals(3, config.cycles)
        assertEquals("program", config.mode)
        assertFalse(config.autonomous)
        assertNull(config.qonstructionName)
        assertFalse(config.useSqrapyard)
        assertEquals("auto", config.containerEngine)
        assertFalse(config.enableTui)
        assertFalse(config.enableWonqrete)
    }

    @Test
    fun `QonQreteRunConfig copy works correctly`() {
        val original = QonQreteRunConfig()
        val modified = original.copy(sensitivity = 10, autonomous = true)
        
        assertEquals(10, modified.sensitivity)
        assertTrue(modified.autonomous)
        assertEquals(6, original.sensitivity)
        assertFalse(original.autonomous)
    }

    // ========================================================================
    // SHELL STATE ENUM TESTS
    // ========================================================================

    @Test
    fun `ShellState enum has all expected values`() {
        val states = ShellState.values()
        assertEquals(4, states.size)
        assertTrue(states.contains(ShellState.NO_BASH))
        assertTrue(states.contains(ShellState.VERIFYING))
        assertTrue(states.contains(ShellState.READY))
        assertTrue(states.contains(ShellState.SHELL_ERROR))
    }

    // ========================================================================
    // RUN STATE ENUM TESTS
    // ========================================================================

    @Test
    fun `RunState enum has all expected values`() {
        val states = RunState.values()
        assertEquals(5, states.size)
        assertTrue(states.contains(RunState.IDLE))
        assertTrue(states.contains(RunState.RUNNING))
        assertTrue(states.contains(RunState.COMPLETED))
        assertTrue(states.contains(RunState.FAILED))
        assertTrue(states.contains(RunState.TIMEOUT))
    }

    // ========================================================================
    // SANITIZE RESULT TESTS
    // ========================================================================

    @Test
    fun `SanitizeResult tracks modifications correctly`() {
        val unchanged = SanitizeResult("test", "test", false)
        assertFalse(unchanged.wasModified)
        assertEquals(unchanged.original, unchanged.sanitized)

        val changed = SanitizeResult("test space", "test_space", true)
        assertTrue(changed.wasModified)
        assertNotEquals(changed.original, changed.sanitized)
    }

    // ========================================================================
    // FILE-BASED TESTS
    // ========================================================================

    @Test
    fun `marker file exit code parsing works`() {
        val markerFile = tempDir.resolve(".qonqrete_run_123.marker").toFile()
        
        // Test success
        markerFile.writeText("0")
        assertEquals(0, markerFile.readText().trim().toIntOrNull())
        
        // Test failure
        markerFile.writeText("1")
        assertEquals(1, markerFile.readText().trim().toIntOrNull())
        
        // Test other exit codes
        markerFile.writeText("127")
        assertEquals(127, markerFile.readText().trim().toIntOrNull())
        
        // Test invalid
        markerFile.writeText("not a number")
        assertNull(markerFile.readText().trim().toIntOrNull())
    }

    @Test
    fun `temp tasq backup and restore flow`() {
        val worqspace = tempDir.resolve("worqspace").toFile()
        worqspace.mkdirs()
        
        val tasqFile = File(worqspace, "tasq.md")
        val backupFile = File(worqspace, ".tasq.md.qonqrete-backup")
        val tempFile = tempDir.resolve("temp-task.md").toFile()
        
        val originalContent = "# Original Task\nDo something"
        tasqFile.writeText(originalContent)
        
        val tempContent = "# Temporary Task\nDo something else"
        tempFile.writeText(tempContent)
        
        // Simulate backup
        tasqFile.copyTo(backupFile, overwrite = true)
        assertTrue(backupFile.exists())
        assertEquals(originalContent, backupFile.readText())
        
        // Simulate copy temp to tasq
        tempFile.copyTo(tasqFile, overwrite = true)
        assertEquals(tempContent, tasqFile.readText())
        
        // Simulate restore
        backupFile.copyTo(tasqFile, overwrite = true)
        backupFile.delete()
        
        assertEquals(originalContent, tasqFile.readText())
        assertFalse(backupFile.exists())
    }

    @Test
    fun `orphan cleanup detects backup file`() {
        val worqspace = tempDir.resolve("worqspace").toFile()
        worqspace.mkdirs()
        
        val backupFile = File(worqspace, ".tasq.md.qonqrete-backup")
        val tasqFile = File(worqspace, "tasq.md")
        
        val backupContent = "# Orphaned backup content"
        backupFile.writeText(backupContent)
        tasqFile.writeText("# Current content")
        
        assertTrue(backupFile.exists())
        assertNotEquals(backupFile.readText(), tasqFile.readText())
        
        // Restore
        backupFile.copyTo(tasqFile, overwrite = true)
        assertEquals(backupContent, tasqFile.readText())
    }

    // ========================================================================
    // QAGE ARTIFACTS TESTS
    // ========================================================================

    @Test
    fun `QageArtifacts totalCount is correct`() {
        val artifacts = QageArtifacts(
            qodeyard = listOf("file1.py", "file2.py"),
            exeq = listOf("cmd1"),
            reqap = listOf("r1", "r2", "r3"),
            briqs = listOf("b1"),
            bloqs = listOf("bl1", "bl2")
        )
        assertEquals(9, artifacts.totalCount)
    }

    @Test
    fun `QageArtifacts empty has zero count`() {
        val artifacts = QageArtifacts(
            qodeyard = emptyList(),
            exeq = emptyList(),
            reqap = emptyList(),
            briqs = emptyList(),
            bloqs = emptyList()
        )
        assertEquals(0, artifacts.totalCount)
    }

    // ========================================================================
    // QAGE SORTING TESTS
    // ========================================================================

    @Test
    fun `qage sorting by timestamp is newest first`() {
        val qages = listOf(
            "qage_20250313_100000",
            "qage_20250313_140000",
            "qage_20250312_235959",
            "qage_20250313_120000"
        )
        
        val sorted = qages.sortedByDescending { QonQreteValidation.parseQageTimestamp(it) ?: 0L }
        
        assertEquals("qage_20250313_140000", sorted[0])
        assertEquals("qage_20250313_120000", sorted[1])
        assertEquals("qage_20250313_100000", sorted[2])
        assertEquals("qage_20250312_235959", sorted[3])
    }
}
