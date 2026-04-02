/**
 * QonQrete Qonstruction Name Dialog
 * Quick dialog for entering qonstruction name
 *
 * @author WoNQ
 * @version 1.2.2
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.Messages
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.services.QonQreteProjectService
import java.awt.BorderLayout
import java.awt.Dimension
import javax.swing.JComponent
import javax.swing.JPanel

class QonQreteQonstructionNameDialog(
    private val project: Project,
    private val service: QonQreteProjectService
) : DialogWrapper(project) {

    private val nameField = JBTextField()
    private var validatedName: String? = null

    init {
        title = "QonQrete: Qonstruction Name"
        init()
    }

    override fun createCenterPanel(): JComponent {
        nameField.toolTipText = "Enter a name for this build (optional)"

        val builder = FormBuilder.createFormBuilder()
            .addLabeledComponent("Qonstruction Name:", nameField)
            .addComponentToRightColumn(JBLabel("(optional, alphanumeric/_/- only)"))
            .addComponentToRightColumn(JBLabel("Leave empty for default naming"))

        val panel = JPanel(BorderLayout())
        panel.add(builder.panel, BorderLayout.CENTER)
        panel.border = JBUI.Borders.empty(10)
        panel.preferredSize = Dimension(400, 100)

        return panel
    }

    override fun getPreferredFocusedComponent() = nameField

    override fun doOKAction() {
        val input = nameField.text.trim()

        if (input.isEmpty()) {
            validatedName = null
            super.doOKAction()
            return
        }

        val result = service.sanitizeQonstructionName(input)

        if (result.wasModified) {
            val confirm = Messages.showYesNoDialog(
                project,
                "Name will be sanitized:\n\n'${result.original}' → '${result.sanitized}'\n\nProceed?",
                "Name Sanitization",
                Messages.getQuestionIcon()
            )
            if (confirm != Messages.YES) {
                return // Don't close dialog
            }
        }

        validatedName = result.sanitized
        super.doOKAction()
    }

    fun getQonstructionName(): String? = validatedName
}
