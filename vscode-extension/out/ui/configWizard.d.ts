/**
 * QonQrete Configuration Wizard
 * Provides VS Code UI dialogs for configuring QonQrete runs
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
 */
import { QonQreteRunConfig } from '../cli/qonqreteRunner';
/**
 * Show the quick configuration wizard
 * Returns the configuration or undefined if cancelled
 */
export declare function showQuickConfigWizard(): Promise<QonQreteRunConfig | undefined>;
/**
 * Show the full configuration wizard with all options
 */
export declare function showFullConfigWizard(): Promise<QonQreteRunConfig | undefined>;
/**
 * Show qonstruction name input dialog
 */
export declare function showQonstructionNameDialog(): Promise<string | undefined>;
/**
 * Show Qage selection dialog
 */
export declare function showQageSelectionDialog(qages: string[]): Promise<string | undefined>;
/**
 * Show clean confirmation dialog
 */
export declare function showCleanConfirmDialog(qages: string[]): Promise<{
    qageName?: string;
    cleanAll: boolean;
} | undefined>;
//# sourceMappingURL=configWizard.d.ts.map