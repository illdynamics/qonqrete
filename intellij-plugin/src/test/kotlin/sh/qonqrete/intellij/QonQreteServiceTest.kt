package sh.qonqrete.intellij

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*
import sh.qonqrete.intellij.services.QonQreteRunConfig
import sh.qonqrete.intellij.util.CommandBuilder
import sh.qonqrete.intellij.util.ShellEscape

class QonQreteServiceTest {

    @Test
    fun `ShellEscape preserves safe strings`() {
        assertEquals("test", ShellEscape.escape("test"))
        assertEquals("path/to/file", ShellEscape.escape("path/to/file"))
    }

    @Test
    fun `ShellEscape quotes unsafe strings`() {
        assertEquals("'my project'", ShellEscape.escape("my project"))
        assertEquals("'it'\\''s'", ShellEscape.escape("it's"))
    }

    @Test
    fun `CommandBuilder run builds qq run command`() {
        val command = CommandBuilder.qq().run("task.md", "/tmp/out", noTui = false).build()
        assertEquals("qq run task.md /tmp/out", command)
    }

    @Test
    fun `CommandBuilder run adds no-tui`() {
        val command = CommandBuilder.qq().run("task.md", "/tmp/out", noTui = true).build()
        assertTrue(command.endsWith("--no-tui"))
    }

    @Test
    fun `CommandBuilder utility commands`() {
        assertTrue(CommandBuilder.qq().doctor().build().endsWith("doctor"))
        assertTrue(CommandBuilder.qq().verify().build().endsWith("verify --skip-package-steps"))
        assertTrue(CommandBuilder.qq().cleanup(".").build().contains("cleanup --repo-root ."))
        assertTrue(CommandBuilder.qq().runs().build().endsWith("runs sessions"))
        assertTrue(CommandBuilder.qq().chat().build().endsWith("chat"))
    }

    @Test
    fun `QonQreteRunConfig defaults`() {
        val config = QonQreteRunConfig(taskFile = "task.md", destinationDir = "/tmp/out")
        assertFalse(config.noTui)
        assertEquals("task.md", config.taskFile)
    }
}
