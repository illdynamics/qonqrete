import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'worqer'))

lib_ai_stub = types.ModuleType('lib_ai')
lib_ai_stub.run_ai_completion = lambda *args, **kwargs: '{"sensitivity": 5, "confidence": "medium", "rationale": ["stub"]}'
sys.modules.setdefault('lib_ai', lib_ai_stub)

import instruqtor  # noqa: E402


class BriqSensitivityTests(unittest.TestCase):
    def test_ranges_cover_full_zero_to_sixteen_scale(self):
        self.assertEqual(instruqtor.clamp_sensitivity(-5), 0)
        self.assertEqual(instruqtor.clamp_sensitivity(99), 16)
        for level in range(17):
            min_b, max_b, target_b, prompt = instruqtor.get_sensitivity_config(level)
            self.assertGreaterEqual(min_b, 1)
            self.assertGreaterEqual(max_b, min_b)
            self.assertGreaterEqual(target_b, min_b)
            self.assertLessEqual(target_b, max_b)
            self.assertIn('BRIQ', prompt)

    def test_ranges_are_bounded_and_monotonic(self):
        previous_target = 0
        previous_max = 0
        for level in range(17):
            min_b, max_b, target_b, _ = instruqtor.get_sensitivity_config(level)
            self.assertGreaterEqual(target_b, previous_target)
            self.assertGreaterEqual(max_b, previous_max)
            previous_target = target_b
            previous_max = max_b

    def test_auto_complexity_estimator_matches_reference_bands(self):
        small = """Create a FastAPI REST API in one file named main.py.
Requirements:
- GET /health
- POST /users
- GET /users
- GET /users/{user_id}
- Include requirements.txt and run.sh
Do not add extra features.
"""
        medium = """# Goal
Build a single-page recipe planner using plain HTML, CSS, and JavaScript.

## Files
- index.html
- styles.css
- app.js

## Layout
- main title
- subtitle
- recipe creation form
- search input
- category filter
- favorites-only toggle
- recipe list or grid
- weekly meal-plan area
- stats area

## Behavior
- create recipes
- delete recipes
- favorite and unfavorite recipes
- expand and collapse long sections
- search across name, ingredients, and steps
- category filter must combine with search
- favorites-only toggle must combine with search and filter
- weekly meal plan for Monday through Sunday
- localStorage persistence
- empty states
- validation and immediate filtering updates

Do not add extra features.
"""
        big = """# Goal
Create a realtime chat webapp with no authentication.

## Required files
- main.py
- schemas.py
- store.py
- chat_routes.py
- file_routes.py
- ws_manager.py
- utils.py
- requirements.txt
- run.sh

## Required behavior
- FastAPI and Pydantic
- WebSockets for realtime chat
- online user list
- direct messages
- file transfer accept and deny flow
- runtime state in memory only
- storage/uploads for delivered files
- minimal frontend UI
- websocket-driven live updates
- separate browser sessions with chosen display names

Do not add authentication or databases.
"""
        huge = """# Platform build plan
Build a repository-scale platform with many directories and many files.

## Repository structure
- Vagrantfile
- bootstrap.sh
- provision/00-base.sh
- provision/01-docker.sh
- provision/02-databases.sh
- provision/03-c2-frameworks.sh
- provision/04-security-tools.sh
# This line was removed to eliminate autowonqnet reference
- provision/06-evasion-tools.sh
- provision/07-custom-env.sh
- provision/99-finalize.sh
- config/config.yaml.example
- config/.env.example
- config/nginx/nginx.conf
- config/nginx/conf.d/default.conf
- src/main.py
- src/shared/constants.py
- src/shared/exceptions.py
- src/shared/logger.py
- src/shared/config_loader.py
- src/shared/types.py
- src/shared/crypto.py
- src/shared/utils.py
- src/safety/crypto_auth.py
- src/safety/geofencing.py
- src/safety/timebomb.py
- src/safety/killswitch.py
- src/safety/scope_validator.py
- src/safety/audit_logger.py
- src/ai/base_capability.py
- src/ai/decision_engine.py
- src/ai/context_manager.py
- src/ai/prompt_templates.py
- src/ai/tool_registry.py
- src/ai/mcp_interface.py
- src/traffic/jitter.py
- src/traffic/dga.py
- src/traffic/domain_fronting.py
- src/traffic/transport_fallback.py
- src/traffic/covert_channels.py
- src/c2/sliver_client.py
- src/c2/havoc_client.py
- src/c2/covenant_client.py
- src/c2/mythic_client.py
- src/c2/unified_c2.py
- src/c2/protocols/encrypted_beacon.py
- src/c2/auth/session_handshake.py
- src/c2/p2p/p2p_network.py
- src/tools/nmap_wrapper.py
- src/tools/httpx_wrapper.py
- src/tools/nuclei_wrapper.py
- src/tools/metasploit_wrapper.py
- src/tools/crackmapexec_wrapper.py
- src/tools/impacket_wrapper.py
- src/tools/sqlmap_wrapper.py
- src/tools/feroxbuster_wrapper.py
- src/tools/tool_orchestrator.py
- src/intel/target_profile.py
- src/intel/credential_store.py
- src/intel/network_map.py
- src/intel/attack_graph.py
- src/intel/campaign_manager.py
- src/factory/implant_builder.py
- src/factory/donut_converter.py
- src/factory/binary_signer.py
- src/factory/scarecrow_wrapper.py
- src/factory/nimcrypt_wrapper.py
- src/factory/obfuscation.py
- src/factory/loader_generator.py
- src/factory/staged_payload.py
- src/factory/complete_agent_factory.py
- src/orchestration/redis_backend.py
- src/orchestration/postgres_backend.py
- src/orchestration/elasticsearch_backend.py
- src/orchestration/session_manager.py
- src/orchestration/event_handler.py
- src/orchestration/scheduler.py
- src/orchestration/beacon_orchestrator.py
- src/orchestration/task_queue.py
- tests/test_shared.py
- tests/test_safety.py
- tests/test_ai.py
- tests/test_c2.py
- tests/test_factory.py
- tests/test_orchestration.py
- docker/docker-compose.yml
- scripts/start-platform.sh
- scripts/stop-platform.sh
- scripts/health-check.sh
- scripts/ai-chat.sh
- scripts/generate-payload.sh

## Requirements
- implement provisioning, orchestration, integrations, helper scripts, validation, and tests
- must be idempotent
- must include docker, vagrant, postgres, redis, neo4j, elasticsearch, nginx, orchestration, payload generation, encrypted beaconing, and C2 integrations
- no stubs or mocks
"""

        self.assertEqual(instruqtor.analyze_task_complexity(small)['suggested_sensitivity'], 1)
        self.assertIn(instruqtor.analyze_task_complexity(medium)['suggested_sensitivity'], {2, 3})
        self.assertIn(instruqtor.analyze_task_complexity(big)['suggested_sensitivity'], {4, 5, 6})
        self.assertGreaterEqual(instruqtor.analyze_task_complexity(huge)['suggested_sensitivity'], 12)


if __name__ == '__main__':
    unittest.main()
