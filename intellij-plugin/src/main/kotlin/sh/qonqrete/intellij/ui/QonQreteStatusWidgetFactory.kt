package sh.qonqrete.intellij.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.wm.StatusBar
import com.intellij.openapi.wm.StatusBarWidget
import com.intellij.openapi.wm.StatusBarWidgetFactory
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.util.Consumer
import sh.qonqrete.intellij.services.QonQreteProjectService
import java.awt.event.MouseEvent

class QonQreteStatusWidgetFactory : StatusBarWidgetFactory {
    override fun getId(): String = "QonQreteStatusWidget"
    override fun getDisplayName(): String = "QonQrete Status"
    override fun isAvailable(project: Project): Boolean = true
    override fun createWidget(project: Project): StatusBarWidget = QonQreteStatusWidget(project)
    override fun disposeWidget(widget: StatusBarWidget) { Disposer.dispose(widget) }
    override fun canBeEnabledOn(statusBar: StatusBar): Boolean = true
}

private class QonQreteStatusWidget(private val project: Project) : StatusBarWidget, StatusBarWidget.TextPresentation {
    override fun ID(): String = "QonQreteStatusWidget"
    override fun install(statusBar: StatusBar) {}
    override fun dispose() {}
    override fun getPresentation(): StatusBarWidget.WidgetPresentation = this
    override fun getText(): String {
        val ready = QonQreteProjectService.getInstance(project).isAvailable()
        return if (ready) "🟢 QonQrete" else "🔴 QonQrete"
    }
    override fun getTooltipText(): String = "Click to open the QonQrete tool window"
    override fun getAlignment(): Float = java.awt.Component.CENTER_ALIGNMENT
    override fun getClickConsumer(): Consumer<MouseEvent> = Consumer {
        ToolWindowManager.getInstance(project).getToolWindow("QonQrete")?.show()
    }
}
