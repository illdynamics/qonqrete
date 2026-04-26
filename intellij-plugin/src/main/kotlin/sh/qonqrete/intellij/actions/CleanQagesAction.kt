/**
 * Clean Qages Action
 * Clean qage directories with confirmation
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.ui.popup.JBPopupFactory
import com.intellij.ui.components.JBList
import sh.qonqrete.intellij.services.*
import java.text.SimpleDateFormat
import java.util.*
import javax.swing.ListSelectionModel

class CleanQagesAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = QonQreteProjectService.getInstance(project)

        // Check shell state
        val (canRun, reason, state) = service.canExecute()
        if (!canRun) {
            when (state) {
                ShellState.VERIFYING -> {
                    service.notify("QonQrete", "Please wait - shell verification in progress...", NotificationType.WARNING)
                }
                ShellState.NO_BASH -> {
                    Messages.showErrorDialog(project, reason, "QonQrete: No Bash Shell")
                }
                ShellState.SHELL_ERROR -> {
                    Messages.showErrorDialog(project, reason, "QonQrete: Shell Error")
                }
                else -> {}
            }
            return
        }

        // Check if QonQrete is available
        if (service.getQonQretePath() == null) {
            Messages.showErrorDialog(
                project,
                "Could not find qonqrete.sh in this project.",
                "QonQrete Not Found"
            )
            return
        }

        // Get available qages
        val qages = service.getAvailableQages()

        if (qages.isEmpty()) {
            Messages.showInfoMessage(
                project,
                "No qages found to clean.",
                "QonQrete: No Qages"
            )
            return
        }

        // Show options
        val options = arrayOf("Clean All Qages", "Select Specific Qage", "Cancel")
        val choice = Messages.showDialog(
            project,
            "Found ${qages.size} qage(s). What would you like to clean?",
            "QonQrete: Clean Qages",
            options,
            0,
            Messages.getQuestionIcon()
        )

        when (choice) {
            0 -> cleanAll(project, service, qages.size)
            1 -> selectAndClean(project, service, qages)
            else -> return
        }
    }

    private fun cleanAll(project: com.intellij.openapi.project.Project, service: QonQreteProjectService, count: Int) {
        val confirm = Messages.showYesNoDialog(
            project,
            "Are you sure you want to delete ALL $count qage(s)?\n\n" +
            "This action cannot be undone.",
            "QonQrete: Confirm Clean All",
            Messages.getWarningIcon()
        )

        if (confirm != Messages.YES) {
            return
        }

        try {
            service.clean(cleanAll = true)
            service.notify("QonQrete", "Cleaning all qages...", NotificationType.INFORMATION)
        } catch (ex: Exception) {
            service.notify("QonQrete Error", "Failed to clean: ${ex.message}", NotificationType.ERROR)
        }
    }

    private fun selectAndClean(project: com.intellij.openapi.project.Project, service: QonQreteProjectService, qages: List<String>) {
        val displayItems = qages.map { qageName ->
            val timestamp = service.parseQageTimestamp(qageName)
            val dateStr = if (timestamp != null) {
                val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm:ss")
                sdf.format(Date(timestamp))
            } else {
                "unknown"
            }
            "$qageName ($dateStr)"
        }

        val list = JBList(displayItems)
        list.selectionMode = ListSelectionModel.SINGLE_SELECTION

        JBPopupFactory.getInstance()
            .createListPopupBuilder(list)
            .setTitle("Select Qage to Clean")
            .setItemChoosenCallback {
                val selectedIndex = list.selectedIndex
                if (selectedIndex >= 0) {
                    val selectedQage = qages[selectedIndex]
                    
                    val confirm = Messages.showYesNoDialog(
                        project,
                        "Delete qage '$selectedQage'?\n\nThis action cannot be undone.",
                        "QonQrete: Confirm Clean",
                        Messages.getWarningIcon()
                    )

                    if (confirm == Messages.YES) {
                        try {
                            service.clean(qageName = selectedQage)
                            service.notify("QonQrete", "Cleaning $selectedQage...", NotificationType.INFORMATION)
                        } catch (ex: Exception) {
                            service.notify("QonQrete Error", "Failed to clean: ${ex.message}", NotificationType.ERROR)
                        }
                    }
                }
            }
            .createPopup()
            .showCenteredInCurrentWindow(project)
    }

    override fun update(e: AnActionEvent) {
        val project = e.project
        val presentation = e.presentation

        if (project == null) {
            presentation.isEnabledAndVisible = false
            return
        }

        val service = QonQreteProjectService.getInstance(project)
        val hasQonqrete = service.getQonQretePath() != null
        val hasQages = service.getAvailableQages().isNotEmpty()
        val (canRun, _, _) = service.canExecute()
        val isRunning = service.getRunStatus().state == RunState.RUNNING

        presentation.isVisible = hasQonqrete
        presentation.isEnabled = hasQonqrete && hasQages && canRun && !isRunning
    }
}
