/**
 * Tasq Editor Notification Provider
 * Shows banner for tasq.md files with run action
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.openapi.fileEditor.FileEditor
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.ui.EditorNotificationPanel
import com.intellij.ui.EditorNotificationProvider
import sh.qonqrete.intellij.services.*
import java.io.File
import java.util.function.Function
import javax.swing.JComponent

class TasqEditorNotificationProvider : EditorNotificationProvider, DumbAware {

    override fun collectNotificationData(
        project: Project,
        file: VirtualFile
    ): Function<in FileEditor, out JComponent?>? {
        // Only show for .md files
        if (file.extension?.lowercase() != "md") {
            return null
        }

        val service = QonQreteProjectService.getInstance(project)
        
        // Check if QonQrete is available in this project
        val qonqretePath = service.getQonQretePath() ?: return null
        val workingDir = File(qonqretePath).parent
        val canonicalTasqPath = "$workingDir/worqspace/tasq.md"

        // Check if this is the canonical tasq.md
        val isCanonicalTasq = try {
            File(file.path).canonicalPath == File(canonicalTasqPath).canonicalPath
        } catch (_: Exception) {
            false
        }

        // Check if this is any tasq.md in the worqspace
        val isInWorqspace = file.path.contains("worqspace")
        val isTasqMd = file.name == "tasq.md"

        return when {
            isCanonicalTasq -> Function { editor ->
                createCanonicalTasqPanel(project, service, editor)
            }
            isTasqMd && isInWorqspace -> Function { editor ->
                createNonCanonicalTasqPanel(project, service, file, editor)
            }
            file.extension?.lowercase() == "md" && service.getQonQretePath() != null -> Function { editor ->
                createMarkdownPanel(project, service, file, editor)
            }
            else -> null
        }
    }

    private fun createCanonicalTasqPanel(
        project: Project,
        service: QonQreteProjectService,
        editor: FileEditor
    ): EditorNotificationPanel {
        val panel = EditorNotificationPanel(editor, EditorNotificationPanel.Status.Info)
        panel.text = "QonQrete canonical tasq.md"

        val (canRun, _, state) = service.canExecute()
        val isRunning = service.getRunStatus().state == RunState.RUNNING

        when {
            state == ShellState.VERIFYING -> {
                panel.text = "QonQrete: Verifying shell..."
            }
            state == ShellState.NO_BASH -> {
                panel.text = "QonQrete: No bash shell available"
            }
            state == ShellState.SHELL_ERROR -> {
                panel.text = "QonQrete: Shell error"
                panel.createActionLabel("Retry") {
                    service.reverifyShell()
                }
            }
            isRunning -> {
                panel.text = "QonQrete: Running..."
            }
            canRun -> {
                panel.createActionLabel("Run Tasq") {
                    com.intellij.openapi.actionSystem.ActionManager.getInstance()
                        .getAction("QonQrete.RunTasq")
                        ?.actionPerformed(
                            com.intellij.openapi.actionSystem.AnActionEvent.createFromDataContext(
                                "QonQrete",
                                null,
                                com.intellij.openapi.actionSystem.DataContext { dataId ->
                                    when {
                                        com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.`is`(dataId) -> project
                                        else -> null
                                    }
                                }
                            )
                        )
                }
            }
        }

        return panel
    }

    private fun createNonCanonicalTasqPanel(
        project: Project,
        service: QonQreteProjectService,
        file: VirtualFile,
        editor: FileEditor
    ): EditorNotificationPanel {
        val panel = EditorNotificationPanel(editor, EditorNotificationPanel.Status.Warning)
        panel.text = "This is not the canonical worqspace/tasq.md"

        val canonicalPath = service.getTasqPath()
        if (canonicalPath != null) {
            panel.createActionLabel("Open canonical tasq.md") {
                val vf = com.intellij.openapi.vfs.LocalFileSystem.getInstance()
                    .refreshAndFindFileByPath(canonicalPath)
                if (vf != null) {
                    com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project)
                        .openFile(vf, true)
                }
            }
        }

        return panel
    }

    private fun createMarkdownPanel(
        project: Project,
        service: QonQreteProjectService,
        file: VirtualFile,
        editor: FileEditor
    ): EditorNotificationPanel? {
        // Only show for markdown files in QonQrete projects
        val (canRun, _, state) = service.canExecute()
        val isRunning = service.getRunStatus().state == RunState.RUNNING

        if (!canRun || isRunning) {
            return null
        }

        val panel = EditorNotificationPanel(editor, EditorNotificationPanel.Status.Info)
        panel.text = "QonQrete workspace detected"
        panel.createActionLabel("Run as QonQrete Tasq") {
            com.intellij.openapi.actionSystem.ActionManager.getInstance()
                .getAction("QonQrete.RunAsQonqreteTasq")
                ?.actionPerformed(
                    com.intellij.openapi.actionSystem.AnActionEvent.createFromDataContext(
                        "QonQrete",
                        null,
                        com.intellij.openapi.actionSystem.DataContext { dataId ->
                            when {
                                com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.`is`(dataId) -> project
                                com.intellij.openapi.actionSystem.CommonDataKeys.VIRTUAL_FILE.`is`(dataId) -> file
                                else -> null
                            }
                        }
                    )
                )
        }

        return panel
    }
}
