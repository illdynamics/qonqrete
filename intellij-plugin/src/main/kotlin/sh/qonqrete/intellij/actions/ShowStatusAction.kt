/**
 * Show Status Action
 * Display QonQrete status dialog
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.util.ui.FormBuilder
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.services.*
import java.awt.BorderLayout
import java.awt.Dimension
import java.text.SimpleDateFormat
import java.util.*
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JTextArea

class ShowStatusAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = QonQreteProjectService.getInstance(project)
        
        StatusDialog(project, service).show()
    }

    override fun update(e: AnActionEvent) {
        val project = e.project
        e.presentation.isEnabledAndVisible = project != null
    }

    private class StatusDialog(
        project: com.intellij.openapi.project.Project,
        private val service: QonQreteProjectService
    ) : DialogWrapper(project) {

        init {
            title = "QonQrete Status"
            init()
        }

        override fun createCenterPanel(): JComponent {
            val shellInfo = service.getShellInfo()
            val runStatus = service.getRunStatus()
            val initStatus = service.isInitialized()
            val version = service.getVersion() ?: "not found"
            val qonqretePath = service.getQonQretePath() ?: "not found"
            val qages = service.getAvailableQages()

            val shellStateStr = when (shellInfo.state) {
                ShellState.NO_BASH -> "❌ No Bash"
                ShellState.VERIFYING -> "⏳ Verifying..."
                ShellState.READY -> "✅ Ready"
                ShellState.SHELL_ERROR -> "⚠️ Error: ${shellInfo.verificationError}"
            }

            val runStateStr = when (runStatus.state) {
                RunState.IDLE -> "Idle"
                RunState.RUNNING -> "🔄 Running..."
                RunState.COMPLETED -> "✅ Completed (exit: ${runStatus.exitCode})"
                RunState.FAILED -> "❌ Failed (exit: ${runStatus.exitCode})"
                RunState.TIMEOUT -> "⏱️ Timeout"
            }

            val initStr = when {
                !initStatus.hasDockerfile -> "❌ No Dockerfile"
                !initStatus.hasImage -> "⚠️ Image not built"
                else -> "✅ Ready (${initStatus.engine})"
            }

            val builder = FormBuilder.createFormBuilder()
                .addLabeledComponent("QonQrete Version:", JBLabel(version))
                .addLabeledComponent("Script Path:", JBLabel(qonqretePath))
                .addSeparator()
                .addLabeledComponent("Shell:", JBLabel("${shellInfo.shellType} @ ${shellInfo.shellPath}"))
                .addLabeledComponent("Shell State:", JBLabel(shellStateStr))
                .addSeparator()
                .addLabeledComponent("Container:", JBLabel(initStr))
                .addLabeledComponent("Run State:", JBLabel(runStateStr))
                .addSeparator()
                .addLabeledComponent("Available Qages:", JBLabel("${qages.size}"))

            if (qages.isNotEmpty()) {
                val qageList = qages.take(5).joinToString("\n") { qageName ->
                    val ts = service.parseQageTimestamp(qageName)
                    val dateStr = if (ts != null) {
                        SimpleDateFormat("yyyy-MM-dd HH:mm").format(Date(ts))
                    } else "?"
                    "  • $qageName ($dateStr)"
                }
                val suffix = if (qages.size > 5) "\n  ... and ${qages.size - 5} more" else ""
                
                val textArea = JTextArea(qageList + suffix)
                textArea.isEditable = false
                textArea.font = JBUI.Fonts.smallFont()
                builder.addComponent(textArea)
            }

            val panel = JPanel(BorderLayout())
            panel.add(builder.panel, BorderLayout.CENTER)
            panel.preferredSize = Dimension(450, 350)
            return panel
        }
    }
}
