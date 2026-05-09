/**
 * Action invoker utility — replaces deprecated ActionUtil.invokeAction.
 *
 * Uses the modern AnAction.actionPerformed(AnActionEvent) pattern
 * instead of the deprecated ActionUtil.invokeAction.
 *
 * @author QonQrete
 * @version VERSION
 * @license Apache-2.0
 */

package sh.qonqrete.intellij.util

import com.intellij.openapi.actionSystem.*
import java.awt.event.InputEvent

/**
 * Invoke an action by ID using the modern actionPerformed approach.
 *
 * This replaces deprecated ActionUtil.invokeAction() calls.
 * Compatible with IntelliJ 2023.3+ (our minimum supported version).
 */
object ActionInvoker {

    /**
     * Invoke an action by its ID with a project-scoped data context.
     * Safe replacement for ActionUtil.invokeAction(action, dataContext, place, inputEvent, modifier)
     */
    fun invokeAction(actionId: String, dataContext: DataContext, place: String = "QonQrete", inputEvent: InputEvent? = null) {
        val action = ActionManager.getInstance().getAction(actionId) ?: return
        val event = AnActionEvent.createFromDataContext(place, null, dataContext)
        action.actionPerformed(event)
    }
}
