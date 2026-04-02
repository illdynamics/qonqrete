/**
 * QonQrete Tool Window Factory
 * Creates the main tool window
 *
 * @author WoNQ
 * @version 1.2.2
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory

class QonQreteToolWindowFactory : ToolWindowFactory {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel = QonQreteToolWindowPanel(project)
        val content = ContentFactory.getInstance().createContent(panel, "", false)
        toolWindow.contentManager.addContent(content)
    }

    override fun shouldBeAvailable(project: Project): Boolean {
        return true
    }
}
