/**
 * Resume Run Action
 * Resume from existing qage with details popup
 * 
 * v1.1.9: Shows timestamps and artifact counts in selection popup
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.popup.JBPopupFactory
import sh.qonqrete.intellij.services.QonQreteProjectService
import sh.qonqrete.intellij.services.QonQreteRunConfig
import java.awt.Component
import javax.swing.DefaultListCellRenderer
import javax.swing.JList

class ResumeRunAction : AnAction() {

    // Data class for qage list items with details
    private data class QageListItem(
        val name: String,
        val timestamp: String,
        val artifactCount: Int
    ) {
        override fun toString() = name
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = QonQreteProjectService.getInstance(project)

        val (canRun, reason, _) = service.canExecute()
        if (!canRun) {
            service.notify("QonQrete", reason ?: "Cannot run", NotificationType.WARNING)
            return
        }

        val qages = service.getAvailableQages()
        if (qages.isEmpty()) {
            service.notify("QonQrete", "No qages found to resume", NotificationType.INFORMATION)
            return
        }

        // Build list items with details
        val qageItems = qages.map { qageName ->
            val timestamp = service.formatQageTimestamp(qageName)
            val details = service.getQageDetails(qageName)
            val artifactCount = details?.artifacts?.totalCount ?: 0
            QageListItem(qageName, timestamp, artifactCount)
        }

        // Custom cell renderer to show details
        val cellRenderer = object : DefaultListCellRenderer() {
            override fun getListCellRendererComponent(
                list: JList<*>?,
                value: Any?,
                index: Int,
                isSelected: Boolean,
                cellHasFocus: Boolean
            ): Component {
                val comp = super.getListCellRendererComponent(list, value, index, isSelected, cellHasFocus)
                if (value is QageListItem) {
                    text = "<html><b>${value.name}</b><br><small>${value.timestamp} • ${value.artifactCount} artifacts</small></html>"
                }
                return comp
            }
        }

        // Create popup list
        val list = JList(qageItems.toTypedArray())
        list.cellRenderer = cellRenderer
        list.fixedCellHeight = 45
        list.selectedIndex = 0

        JBPopupFactory.getInstance()
            .createListPopupBuilder(list)
            .setTitle("Resume from Qage")
            .setMovable(true)
            .setResizable(true)
            .setItemChoosenCallback {
                val selected = list.selectedValue as? QageListItem
                if (selected != null) {
                    try {
                        val config = QonQreteRunConfig.fromSettings()
                        service.resume(selected.name, config)
                    } catch (ex: Exception) {
                        service.notify("QonQrete Error", ex.message ?: "Unknown error", NotificationType.ERROR)
                    }
                }
            }
            .createPopup()
            .showInFocusCenter()
    }

    override fun update(e: AnActionEvent) {
        val project = e.project
        if (project == null) {
            e.presentation.isEnabled = false
            return
        }
        val service = QonQreteProjectService.getInstance(project)
        val (canRun, _, _) = service.canExecute()
        val hasQonqrete = service.getQonQretePath() != null
        val hasQages = service.getAvailableQages().isNotEmpty()
        e.presentation.isEnabled = canRun && hasQonqrete && hasQages
    }
}
