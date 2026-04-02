/**
 * Create Tasq Action
 * Creates a starter tasq.md at project root
 *
 * @author WoNQ
 * @version 1.2.2
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.vfs.LocalFileSystem
import sh.qonqrete.intellij.services.QonQreteProjectService
import java.io.File

class CreateTasqAction : AnAction() {

    companion object {
        private val TASQ_TEMPLATE = """
# TasQ - Define Your Objective

<!--
Welcome to QonQrete! Define your task below.
This file lives at your project root for easy editing.
When you run QonQrete, it gets synced into the runtime automatically.

Tips for a good TasQ:
- Be specific about what you want to build
- Include file/folder structure if you have preferences
- Mention any specific libraries or frameworks
- Define success criteria

Example:
Create a Python CLI tool that:
1. Reads a CSV file from command line argument
2. Generates a summary report with statistics
3. Saves the report as JSON

Requirements:
- Use argparse for CLI
- Use pandas for data processing
- Include error handling for missing files
- Write unit tests
-->

## Your TasQ:



""".trimIndent()
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val basePath = project.basePath ?: return
        val tasqFile = File(basePath, "tasq.md")

        val wasCreated = !tasqFile.exists()
        if (wasCreated) {
            tasqFile.writeText(TASQ_TEMPLATE)
        }

        // Open in editor
        val vf = LocalFileSystem.getInstance().refreshAndFindFileByPath(tasqFile.absolutePath)
        if (vf != null) {
            FileEditorManager.getInstance(project).openFile(vf, true)
        }

        if (wasCreated) {
            QonQreteProjectService.getInstance(project)
                .notify("QonQrete", "tasq.md created! Edit it and run QonQrete when ready.", com.intellij.notification.NotificationType.INFORMATION)
        }
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project?.basePath != null
    }
}
