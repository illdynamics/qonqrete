/**
 * QonQrete Status Widget Factory
 * Status bar widget showing shell state, run state, and version
 * 
 * v1.1.9: Now shows version in widget text
 *
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.wm.StatusBar
import com.intellij.openapi.wm.StatusBarWidget
import com.intellij.openapi.wm.StatusBarWidgetFactory
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.util.Consumer
import sh.qonqrete.intellij.services.*
import java.awt.Component
import java.awt.event.MouseEvent

class QonQreteStatusWidgetFactory : StatusBarWidgetFactory {

    override fun getId(): String = "QonQreteStatusWidget"
    override fun getDisplayName(): String = "QonQrete Status"
    override fun isAvailable(project: Project): Boolean = true

    override fun createWidget(project: Project): StatusBarWidget {
        return QonQreteStatusWidget(project)
    }

    override fun disposeWidget(widget: StatusBarWidget) {
        Disposer.dispose(widget)
    }

    override fun canBeEnabledOn(statusBar: StatusBar): Boolean = true
}

private class QonQreteStatusWidget(private val project: Project) : StatusBarWidget, StatusBarWidget.TextPresentation {

    private var statusBar: StatusBar? = null
    private val service by lazy { QonQreteProjectService.getInstance(project) }

    override fun ID(): String = "QonQreteStatusWidget"

    override fun install(statusBar: StatusBar) {
        this.statusBar = statusBar
        service.onShellStateChange { statusBar.updateWidget(ID()) }
        service.onRunStateChange { statusBar.updateWidget(ID()) }
    }

    override fun dispose() {
        statusBar = null
    }

    override fun getPresentation(): StatusBarWidget.WidgetPresentation = this

    override fun getText(): String {
        val shellInfo = service.getShellInfo()
        val runStatus = service.getRunStatus()
        val version = service.getVersion()
        
        val versionText = version?.let { "v$it" } ?: ""
        
        val stateIcon = when {
            runStatus.state == RunState.RUNNING -> "🔄"
            runStatus.state == RunState.COMPLETED -> "✅"
            runStatus.state == RunState.FAILED -> "❌"
            shellInfo.state == ShellState.READY -> "🟢"
            shellInfo.state == ShellState.NO_BASH -> "🔴"
            shellInfo.state == ShellState.SHELL_ERROR -> "🟠"
            else -> "⏳"
        }
        
        return "$stateIcon QonQrete $versionText"
    }

    override fun getTooltipText(): String {
        val shellInfo = service.getShellInfo()
        val runStatus = service.getRunStatus()
        val version = service.getVersion() ?: "unknown"
        
        val shellStatus = when (shellInfo.state) {
            ShellState.NO_BASH -> "No bash found"
            ShellState.VERIFYING -> "Verifying shell..."
            ShellState.READY -> "Shell: ${shellInfo.shellType} (ready)"
            ShellState.SHELL_ERROR -> "Shell error: ${shellInfo.verificationError}"
        }
        
        val runStatusText = when (runStatus.state) {
            RunState.IDLE -> "Idle"
            RunState.RUNNING -> "Running..."
            RunState.COMPLETED -> "Completed (exit ${runStatus.exitCode})"
            RunState.FAILED -> "Failed (exit ${runStatus.exitCode})"
            RunState.TIMEOUT -> "Timeout"
        }
        
        return """
            |QonQrete v$version
            |$shellStatus
            |Run: $runStatusText
            |Click to open tool window
        """.trimMargin()
    }

    override fun getAlignment(): Float = Component.CENTER_ALIGNMENT

    override fun getClickConsumer(): Consumer<MouseEvent> = Consumer {
        ToolWindowManager.getInstance(project).getToolWindow("QonQrete")?.show()
    }
}
