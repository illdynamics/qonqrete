/**
 * QonQrete v2 tool window panel.
 */
package sh.qonqrete.intellij.ui

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBLabel
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.services.QonQreteProjectService
import sh.qonqrete.intellij.services.QonQreteSettingsState
import sh.qonqrete.intellij.util.QonQreteConfig
import java.awt.BorderLayout
import java.awt.Dimension
import java.awt.FlowLayout
import javax.swing.Box
import javax.swing.BoxLayout
import javax.swing.JButton
import javax.swing.JPanel
import javax.swing.border.TitledBorder

class QonQreteToolWindowPanel(private val project: Project) : JPanel(BorderLayout()), Disposable {

    private val service = QonQreteProjectService.getInstance(project)
    private val settings = QonQreteSettingsState.getInstance()

    private val providerLabel = JBLabel("…")
    private val modelLabel = JBLabel("…")
    private val destinationLabel = JBLabel("…")
    private val availabilityLabel = JBLabel("…")

    private val runButton = JButton("▶ Run Open Task File")
    private val runFileButton = JButton("▶ Run Task File…")
    private val chatButton = JButton("💬 Chat")
    private val configureButton = JButton("🤖 Provider & Model")
    private val openConfigButton = JButton("📄 Open Config")
    private val doctorButton = JButton("🩺 Doctor")
    private val verifyButton = JButton("✅ Verify")
    private val cleanupButton = JButton("🧹 Cleanup")
    private val runsButton = JButton("📜 List Runs")
    private val replayButton = JButton("↺ Replay Run")
    private val execButton = JButton("⌨ Exec")

    init {
        border = JBUI.Borders.empty(8)
        buildUI()
        bindButtons()
        refresh()
    }

    private fun buildUI() {
        val main = JPanel()
        main.layout = BoxLayout(main, BoxLayout.Y_AXIS)

        val status = JPanel(BorderLayout())
        status.border = TitledBorder("Status")
        val statusBox = JPanel()
        statusBox.layout = BoxLayout(statusBox, BoxLayout.Y_AXIS)
        statusBox.add(row("Provider", providerLabel))
        statusBox.add(row("Model", modelLabel))
        statusBox.add(row("Destination", destinationLabel))
        statusBox.add(row("CLI", availabilityLabel))
        status.add(statusBox, BorderLayout.NORTH)
        main.add(status)
        main.add(Box.createVerticalStrut(6))

        val build = JPanel(FlowLayout(FlowLayout.LEFT))
        build.add(runButton)
        build.add(runFileButton)
        build.add(chatButton)
        build.add(execButton)
        main.add(section("Build", build))
        main.add(Box.createVerticalStrut(6))

        val setup = JPanel(FlowLayout(FlowLayout.LEFT))
        setup.add(configureButton)
        setup.add(openConfigButton)
        main.add(section("Setup", setup))
        main.add(Box.createVerticalStrut(6))

        val diag = JPanel(FlowLayout(FlowLayout.LEFT))
        diag.add(doctorButton)
        diag.add(verifyButton)
        diag.add(cleanupButton)
        main.add(section("Diagnostics", diag))
        main.add(Box.createVerticalStrut(6))

        val runs = JPanel(FlowLayout(FlowLayout.LEFT))
        runs.add(runsButton)
        runs.add(replayButton)
        main.add(section("Runs", runs))

        val scroll = com.intellij.ui.components.JBScrollPane(main)
        scroll.border = null
        scroll.preferredSize = Dimension(250, 500)
        add(scroll, BorderLayout.CENTER)
    }

    private fun section(title: String, content: JPanel): JPanel {
        val wrapper = JPanel(BorderLayout())
        wrapper.border = TitledBorder(title)
        wrapper.add(content, BorderLayout.NORTH)
        wrapper.maximumSize = Dimension(Int.MAX_VALUE, wrapper.preferredSize.height)
        return wrapper
    }

    private fun row(label: String, value: JBLabel): JPanel {
        val p = JPanel(FlowLayout(FlowLayout.LEFT, 4, 2))
        p.add(JBLabel("$label:"))
        p.add(value)
        return p
    }

    private fun bindButtons() {
        runButton.addActionListener {
            com.intellij.openapi.actionSystem.ActionManager.getInstance()
                .getAction("QonQrete.RunCurrentFile")?.let { action ->
                    action.actionPerformed(com.intellij.openapi.actionSystem.AnActionEvent.createFromDataContext(
                        "QonQrete", action.templatePresentation.clone(),
                        com.intellij.openapi.actionSystem.DataContext { id ->
                            when {
                                com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.`is`(id) -> project
                                else -> null
                            }
                        }
                    ))
                }
        }
        runFileButton.addActionListener { runAction("QonQrete.RunTaskFile") }
        chatButton.addActionListener { runAction("QonQrete.Chat") }
        configureButton.addActionListener { runAction("QonQrete.Configure") }
        openConfigButton.addActionListener { runAction("QonQrete.OpenConfig") }
        doctorButton.addActionListener { runAction("QonQrete.Doctor") }
        verifyButton.addActionListener { runAction("QonQrete.Verify") }
        cleanupButton.addActionListener { runAction("QonQrete.Cleanup") }
        runsButton.addActionListener { runAction("QonQrete.Runs") }
        replayButton.addActionListener { runAction("QonQrete.Replay") }
        execButton.addActionListener { runAction("QonQrete.Exec") }
    }

    private fun runAction(id: String) {
        com.intellij.openapi.actionSystem.ActionManager.getInstance().getAction(id)?.let { action ->
            action.actionPerformed(com.intellij.openapi.actionSystem.AnActionEvent.createFromDataContext(
                "QonQrete", action.templatePresentation.clone(),
                com.intellij.openapi.actionSystem.DataContext { dataId ->
                    when {
                        com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.`is`(dataId) -> project
                        else -> null
                    }
                }
            ))
        }
    }

    fun refresh() {
        ApplicationManager.getApplication().invokeLater {
            val cfg = QonQreteConfig.readProviderAndModel(project)
            providerLabel.text = cfg?.first ?: "?"
            modelLabel.text = cfg?.second ?: "?"
            destinationLabel.text = settings.destinationDir.ifBlank { project.basePath ?: "(not set)" }
            availabilityLabel.text = if (service.isAvailable()) "ready" else "missing"
        }
    }

    override fun dispose() {}
}
