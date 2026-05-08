/**
 * Apply first-launch setup: deploy runtime, write config, store API key, run init
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { SetupResult } from '../ui/firstLaunchWizard';
import { storeSecret, PROVIDERS } from '../secrets';
import { getRunner } from '../cli/qonqreteRunner';

const AI_AGENTS = ['qrystallizer', 'instruqtor', 'construqtor', 'inspeqtor'] as const;

/**
 * Update config.yaml for all 4 agents with the chosen provider + model.
 */
function updateConfigYaml(workingDir: string, providerId: string, model: string): boolean {
    const configPath = path.join(workingDir, 'worqspace', 'config.yaml');
    if (!fs.existsSync(configPath)) {
        console.log(`[QonQrete] config.yaml not found at ${configPath}`);
        return false;
    }

    // Map UI provider ID to config provider ID
    const configProviderMap: Record<string, string> = {
        openai: 'openai',
        codex: 'openai',
        google: 'gemini',
        'gemini-cli': 'gemini',
        anthropic: 'anthropic',
        'claude-code': 'anthropic',
        deepseek: 'deepseek',
        codeseeq: 'codeseeq',
        qwen: 'qwen',
        venice: 'venice',
        openrouter: 'openrouter',
        mlx: 'mlx',
        'llama-cpp': 'llama-cpp',
    };

    const configProvider = configProviderMap[providerId] || providerId;

    try {
        const lines = fs.readFileSync(configPath, 'utf8').split('\n');
        const result: string[] = [];
        let inAgent = false;
        let providerSet = false;
        let modelSet = false;
        let currentAgent = '';

        for (const line of lines) {
            // Detect agent sections
            const agentMatch = line.match(/^\s{2}([a-z]+):\s*$/);
            if (agentMatch && AI_AGENTS.includes(agentMatch[1] as any)) {
                // Flush previous agent section if needed
                if (inAgent && !modelSet && model) {
                    result.push(`    model: ${model}`);
                }
                currentAgent = agentMatch[1];
                inAgent = true;
                providerSet = false;
                modelSet = false;
                result.push(line);
                continue;
            }

            if (inAgent) {
                // End of agent section
                if (line.match(/^\s{2}[a-z]+:\s*$/) && !line.match(new RegExp(`^\\s{2}${currentAgent}:\\s*$`))) {
                    if (!modelSet && model) {
                        result.push(`    model: ${model}`);
                    }
                    inAgent = false;
                }
                // Provider line
                if (inAgent && line.match(/^\s{4}provider:\s*\S+/) && !providerSet) {
                    result.push(`    provider: ${configProvider}`);
                    providerSet = true;
                    continue;
                }
                // Model line
                if (inAgent && line.match(/^\s{4}model:\s*\S+/) && !modelSet) {
                    if (model) {
                        result.push(`    model: ${model}`);
                    }
                    modelSet = true;
                    continue;
                }
                // Any other top-level key ends the section
                if (line.match(/^\s{0,2}\S/) && !line.match(/^\s{4}/)) {
                    if (inAgent && !modelSet && model) {
                        result.push(`    model: ${model}`);
                    }
                    inAgent = false;
                }
            }

            result.push(line);
        }

        // Handle last agent section
        if (inAgent && !modelSet && model) {
            result.push(`    model: ${model}`);
        }

        fs.writeFileSync(configPath, result.join('\n'), 'utf8');
        console.log(`[QonQrete] Updated config.yaml: provider=${configProvider}, model=${model}`);
        return true;
    } catch (err) {
        console.error(`[QonQrete] Failed to update config.yaml:`, err);
        return false;
    }
}

/**
 * Apply the first-launch setup:
 * 1. Deploy .qonqrete/ if missing (call existing deploy logic)
 * 2. Write API key to SecretStorage
 * 3. Update config.yaml for all 4 agents
 * 4. Add .qonqrete/ to .gitignore
 * 5. Create starter tasq.md if missing
 * 6. Run .qonqrete/qonqrete.sh init
 */
export async function applySetup(
    setup: SetupResult,
    _context: vscode.ExtensionContext
): Promise<boolean> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        vscode.window.showErrorMessage('No workspace folder open. Please open a project first.');
        return false;
    }

    const wsRoot = workspaceFolders[0].uri.fsPath;
    const qonqreteDir = path.join(wsRoot, '.qonqrete');
    const runner = getRunner();

    try {
        // 1. Deploy runtime if not already present
        const isDeployed = fs.existsSync(path.join(qonqreteDir, 'qonqrete.sh'));
        if (!isDeployed) {
            vscode.window.showInformationMessage('Deploying QonQrete runtime...');
            await vscode.commands.executeCommand('qonqrete.deployToWorkspace');
            // Give deploy a moment
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        // 2. Store API key in SecretStorage
        await storeSecret(setup.envKey, setup.apiKey);
        console.log(`[QonQrete] Stored API key for ${setup.envKey}`);

        // 3. Update config.yaml
        const workingDir = await runner.getQonQreteWorkingDir();
        if (workingDir) {
            updateConfigYaml(workingDir, setup.provider, setup.model);
        }

        // 4. Add .qonqrete/ to .gitignore
        await runner.ensureGitignore();

        // 5. Create starter tasq.md if missing
        const rootTasq = path.join(wsRoot, 'tasq.md');
        if (!fs.existsSync(rootTasq)) {
            const starterTasq = [
                '# QonQrete Starter Tasq',
                '',
                '> Welcome to QonQrete! Replace this with your own task.',
                '',
                '## Goal',
                'Describe what you want to build or fix.',
                '',
                '## Context',
                'Any relevant background, constraints, or preferences.',
                '',
                '## Acceptance',
                '- [ ] Criterion 1',
                '- [ ] Criterion 2',
                '',
                '## Notes',
                'Add any additional guidance for the AI agents.',
                '',
            ].join('\n');
            fs.writeFileSync(rootTasq, starterTasq, 'utf8');
        }

        // 6. Run init
        const scriptPath = path.join(qonqreteDir, 'qonqrete.sh');
        if (fs.existsSync(scriptPath)) {
            try {
                const { execSync } = require('child_process');
                const env = { ...process.env };
                // Inject the API key into the environment
                env[setup.envKey] = setup.apiKey;
                // Gemini/Google equivalence
                if (setup.envKey === 'GOOGLE_API_KEY') {
                    env['GEMINI_API_KEY'] = setup.apiKey;
                }

                execSync(`bash "${scriptPath}" init`, {
                    cwd: wsRoot,
                    env,
                    stdio: 'pipe',
                    timeout: 300000, // 5 minutes for Docker image build
                });
            } catch (initErr: any) {
                console.log(`[QonQrete] init encountered issues: ${initErr.message}`);
                // Non-fatal — user can retry
            }
        }

        // Post-init message
        const providerLabel = PROVIDERS[setup.provider]?.label || setup.provider;
        vscode.window.showInformationMessage(
            `✅ QonQrete is ready! Provider: ${providerLabel}, Model: ${setup.model}. Open any .md file and run "QonQrete: Run Markdown as Task".`,
            'Create Task File',
            'OK'
        ).then(choice => {
            if (choice === 'Create Task File') {
                vscode.commands.executeCommand('qonqrete.createTasq');
            }
        });

        return true;

    } catch (err) {
        console.error(`[QonQrete] applySetup failed:`, err);
        vscode.window.showErrorMessage(
            `Setup encountered an issue: ${err instanceof Error ? err.message : String(err)}`
        );
        return false;
    }
}
