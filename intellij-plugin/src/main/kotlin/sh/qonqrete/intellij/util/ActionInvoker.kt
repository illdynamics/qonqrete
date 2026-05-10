/**
 * Action invoker utility — replaces deprecated ActionUtil.invokeAction.
 *
 * Uses ActionManager.tryToExecute() — the modern, supported invocation path
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
 * Invoke an action by ID using the modern tryToExecute approach.
 *
 * This replaces deprecated ActionUtil.invokeAction() calls.
 * Uses ActionManager.tryToExecute() — the modern non-deprecated invocation path.
 * Constructs AnActionEvent directly instead of deprecated createFromDataContext().
 * Compatible with IntelliJ 2023.3+ (our minimum supported version).
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
        val event = AnActionEvent(
            inputEvent,
            dataContext,
            place,
            presentation,
            actionManager,
            0
        )
        action.beforeActionPerformedUpdate(event)
        if (event.presentation.isEnabled) {
            ActionManager.getInstance().tryToExecute(action, event.inputEvent, null, place, true)
        }
    }
}
