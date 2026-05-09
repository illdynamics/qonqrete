/**
 * Tasq Editor Notification Provider
 * Shows banner for tasq.md files with run action
 *
 * v1.3.0: Canonical tasq is now <project>/tasq.md (workspace root),
 * NOT the internal .qonqrete/worqspace/tasq.md
 *
 * @author WoNQ
 * @version VERSION
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
        if (file.extension?.lowercase() != "md") return null

        val service = QonQreteProjectService.getInstance(project)
        service.getQonQretePath() ?: return null
        val basePath = project.basePath ?: return null

        // Canonical tasq is the ROOT tasq.md
        val rootTasqPath = "$basePath/tasq.md"
        val isRootTasq = try {
            File(file.path).canonicalPath == File(rootTasqPath).canonicalPath
        } catch (_: Exception) { false }

        val isInternalTasq = file.path.contains(".qonqrete") && file.path.contains("worqspace") && file.name == "tasq.md"
        val isOtherWorqspaceTasq = !isRootTasq && !isInternalTasq && file.name == "tasq.md" && file.path.contains("worqspace")

        return when {
            isRootTasq -> Function { editor -> createCanonicalTasqPanel(project, service, editor) }
            isInternalTasq -> Function { editor -> createInternalTasqPanel(project, editor, rootTasqPath) }
            isOtherWorqspaceTasq -> Function { editor -> createNonCanonicalTasqPanel(project, editor, rootTasqPath) }
            else -> Function { editor -> createMarkdownPanel(project, service, file, editor) }
        }
    }

    private fun createCanonicalTasqPanel(
        project: Project,
        service: QonQreteProjectService,
        editor: FileEditor
    ): EditorNotificationPanel {
        val panel = EditorNotificationPanel(editor, EditorNotificationPanel.Status.Info)
        panel.text = "QonQrete tasq.md \u2014 edit your task here"

        val (canRun, _, state) = service.canExecute()
        val isRunning = service.getRunStatus().state == RunState.RUNNING

        when {
            state == ShellState.VERIFYING -> panel.text = "QonQrete: Verifying shell..."
            state == ShellState.NO_BASH -> panel.text = "QonQrete: No bash shell available"
            state == ShellState.SHELL_ERROR -> {
                panel.text = "QonQrete: Shell error"
                panel.createActionLabel("Retry") { service.reverifyShell() }
            }
            isRunning -> panel.text = "QonQrete: Running..."
            canRun -> {
                panel.createActionLabel("Run Tasq") {
                    val runAction = com.intellij.openapi.actionSystem.ActionManager.getInstance()
                        .getAction("QonQrete.RunTasq")
                    if (runAction != null) {
                        runAction.actionPerformed(
                            com.intellij.openapi.actionSystem.AnActionEvent.createFromDataContext(
                                "QonQrete", null,
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
        }
        return panel
    }

    private fun createInternalTasqPanel(
        project: Project,
        editor: FileEditor,
        rootTasqPath: String
    ): EditorNotificationPanel {
        val panel = EditorNotificationPanel(editor, EditorNotificationPanel.Status.Warning)
        panel.text = "This is the internal runtime copy \u2014 edit the root tasq.md instead"

        if (File(rootTasqPath).exists()) {
            panel.createActionLabel("Open root tasq.md") {
                val vf = com.intellij.openapi.vfs.LocalFileSystem.getInstance().refreshAndFindFileByPath(rootTasqPath)
                if (vf != null) com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project).openFile(vf, true)
            }
        } else {
            panel.createActionLabel("Create root tasq.md") {
                val createAction = com.intellij.openapi.actionSystem.ActionManager.getInstance()
                    .getAction("QonQrete.CreateTasq")
                if (createAction != null) {
                    createAction.actionPerformed(
                        com.intellij.openapi.actionSystem.AnActionEvent.createFromDataContext(
                            "QonQrete", null,
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
        editor: FileEditor,
        rootTasqPath: String
    ): EditorNotificationPanel {
        val panel = EditorNotificationPanel(editor, EditorNotificationPanel.Status.Warning)
        panel.text = "This is not the project root tasq.md"

        if (File(rootTasqPath).exists()) {
            panel.createActionLabel("Open root tasq.md") {
                val vf = com.intellij.openapi.vfs.LocalFileSystem.getInstance().refreshAndFindFileByPath(rootTasqPath)
                if (vf != null) com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project).openFile(vf, true)
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
        val (canRun, _, _) = service.canExecute()
        val isRunning = service.getRunStatus().state == RunState.RUNNING
        if (!canRun || isRunning) return null

        val panel = EditorNotificationPanel(editor, EditorNotificationPanel.Status.Info)
        panel.text = "QonQrete project detected"
        panel.createActionLabel("Run as QonQrete Tasq") {
            val runAction = com.intellij.openapi.actionSystem.ActionManager.getInstance()
                .getAction("QonQrete.RunAsQonqreteTasq")
            if (runAction != null) {
                runAction.actionPerformed(
                    com.intellij.openapi.actionSystem.AnActionEvent.createFromDataContext(
                        "QonQrete", null,
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
        return panel
    }
}
