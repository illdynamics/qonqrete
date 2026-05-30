/**
 * Action invoker utility — replaces deprecated ActionUtil.invokeAction.
 *
 * Uses AnActionEvent.createFromDataContext() — the modern, supported path
 * instead of the removed AnActionEvent.createFromInputEvent().
 *
 * @author QonQrete
 * @version VERSION
 * @license Apache-2.0
 */

package sh.qonqrete.intellij.util

import com.intellij.openapi.actionSystem.*
import java.awt.event.InputEvent

/**
 * Invoke an action by ID using createFromDataContext + actionPerformed.
 *
 * This replaces deprecated ActionUtil.invokeAction() calls.
 * Uses AnActionEvent.createFromDataContext() (non-deprecated factory)
 * instead of the removed createFromInputEvent().
 * Does NOT call the override-only AnAction.update().
 * Compatible with IntelliJ 2025.3+ (our minimum supported version).
 */
object ActionInvoker {

    /**
     * Invoke an action by its ID with a project-scoped data context.
     * Safe replacement for ActionUtil.invokeAction(action, dataContext, place, inputEvent, modifier)
     */
    fun invokeAction(actionId: String, dataContext: DataContext, place: String = "QonQrete", inputEvent: InputEvent? = null) {
        val actionManager = ActionManager.getInstance()
        val action = actionManager.getAction(actionId) ?: return
        val presentation = action.templatePresentation.clone()
        // createFromDataContext is the non-deprecated factory in 2025.3+
        val event = AnActionEvent.createFromDataContext(place, presentation, dataContext)
        // Direct actionPerformed — avoids the override-only update() call
        action.actionPerformed(event)
    }
}
