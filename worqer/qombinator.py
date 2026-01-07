#!/usr/bin/env python3
"""Qombinator: Evolutionary Synthesis Agent (Tier 2) - Multi-source code combination"""

import re
from typing import List, Optional
from worqer.mindstaq import CrystallizedIntent


class Qombinator:
    """Evolutionary synthesis for Tier 2. Combines patterns for complex tasks."""
    
    COMPLEX_PATTERNS = {
        'rest_api_crud': '''from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


@dataclass
class Entity:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


class Repository:
    def __init__(self):
        self._storage: Dict[str, Dict] = {}
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        entity_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        entity = {'id': entity_id, 'created_at': now, 'updated_at': now, **data}
        self._storage[entity_id] = entity
        return entity
    
    def get(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return self._storage.get(entity_id)
    
    def get_all(self) -> List[Dict[str, Any]]:
        return list(self._storage.values())
    
    def update(self, entity_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if entity_id not in self._storage:
            return None
        self._storage[entity_id].update(data)
        self._storage[entity_id]['updated_at'] = datetime.utcnow().isoformat()
        return self._storage[entity_id]
    
    def delete(self, entity_id: str) -> bool:
        if entity_id in self._storage:
            del self._storage[entity_id]
            return True
        return False


class APIHandler:
    def __init__(self):
        self.repo = Repository()
    
    def handle_get_all(self) -> Dict[str, Any]:
        return {'status': 'success', 'data': self.repo.get_all()}
    
    def handle_get_one(self, entity_id: str) -> Dict[str, Any]:
        entity = self.repo.get(entity_id)
        return {'status': 'success', 'data': entity} if entity else {'status': 'error', 'message': 'Not found'}
    
    def handle_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {'status': 'success', 'data': self.repo.create(data)}
    
    def handle_update(self, entity_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        entity = self.repo.update(entity_id, data)
        return {'status': 'success', 'data': entity} if entity else {'status': 'error', 'message': 'Not found'}
    
    def handle_delete(self, entity_id: str) -> Dict[str, Any]:
        return {'status': 'success', 'message': 'Deleted'} if self.repo.delete(entity_id) else {'status': 'error', 'message': 'Not found'}
''',
        'async_worker_pool': '''import asyncio
from typing import List, Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    func: Callable = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = None


class AsyncWorkerPool:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.results: dict = {}
        self.running = False
    
    async def start(self):
        self.running = True
        return [asyncio.create_task(self._worker(i)) for i in range(self.max_workers)]
    
    async def stop(self):
        self.running = False
    
    async def submit(self, func: Callable, *args, **kwargs) -> str:
        task = Task(func=func, args=args, kwargs=kwargs)
        await self.queue.put(task)
        return task.id
    
    async def get_result(self, task_id: str) -> Optional[Any]:
        return self.results.get(task_id)
    
    async def _worker(self, worker_id: int):
        while self.running:
            try:
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                try:
                    if asyncio.iscoroutinefunction(task.func):
                        task.result = await task.func(*task.args, **task.kwargs)
                    else:
                        task.result = task.func(*task.args, **task.kwargs)
                except Exception as e:
                    task.error = str(e)
                finally:
                    task.completed_at = datetime.utcnow()
                    self.results[task.id] = task
                    self.queue.task_done()
            except asyncio.TimeoutError:
                continue
''',
        'event_system': '''from typing import Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid
from collections import defaultdict


@dataclass
class Event:
    type: str
    data: Dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {'id': self.id, 'type': self.type, 'data': self.data, 'timestamp': self.timestamp.isoformat()}


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._history: List[Event] = []
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
    
    def publish(self, event_type: str, data: Dict[str, Any] = None) -> Event:
        event = Event(type=event_type, data=data or {})
        self._history.append(event)
        for handler in self._subscribers[event_type] + self._subscribers['*']:
            try:
                handler(event)
            except Exception as e:
                print(f"Handler error: {e}")
        return event


event_bus = EventBus()
''',
        'state_machine': '''from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass


@dataclass
class Transition:
    from_state: str
    to_state: str
    event: str
    condition: Optional[Callable[..., bool]] = None
    action: Optional[Callable[..., Any]] = None


class StateMachine:
    def __init__(self, initial_state: str):
        self.current_state = initial_state
        self.transitions: Dict[str, List[Transition]] = {}
        self.on_enter: Dict[str, Callable] = {}
        self.on_exit: Dict[str, Callable] = {}
        self.history: List[str] = [initial_state]
    
    def add_transition(self, from_state: str, to_state: str, event: str,
                       condition: Callable[..., bool] = None, action: Callable[..., Any] = None):
        key = f"{from_state}:{event}"
        if key not in self.transitions:
            self.transitions[key] = []
        self.transitions[key].append(Transition(from_state, to_state, event, condition, action))
    
    def trigger(self, event: str, **context) -> bool:
        key = f"{self.current_state}:{event}"
        for transition in self.transitions.get(key, []):
            if transition.condition and not transition.condition(**context):
                continue
            if self.current_state in self.on_exit:
                self.on_exit[self.current_state](**context)
            if transition.action:
                transition.action(**context)
            self.current_state = transition.to_state
            self.history.append(self.current_state)
            if self.current_state in self.on_enter:
                self.on_enter[self.current_state](**context)
            return True
        return False
''',
    }
    
    PATTERN_MATCHERS = {
        'rest_api_crud': [r'rest.*api', r'crud.*api', r'full.*api', r'api.*endpoint'],
        'async_worker_pool': [r'async.*worker', r'worker.*pool', r'parallel.*task', r'task.*queue'],
        'event_system': [r'event.*bus', r'pub.*sub', r'event.*driven', r'event.*system'],
        'state_machine': [r'state.*machine', r'fsm', r'finite.*state', r'workflow'],
    }
    
    def __init__(self, config: dict = None):
        self.config = config or {}
    
    def synthesize(self, intent: CrystallizedIntent, prompt: str, context_files: List[str] = None) -> Optional[str]:
        pattern_name = self._find_complex_pattern(intent, prompt)
        if pattern_name and pattern_name in self.COMPLEX_PATTERNS:
            return self._customize_code(self.COMPLEX_PATTERNS[pattern_name], intent, prompt)
        return None
    
    def _find_complex_pattern(self, intent: CrystallizedIntent, prompt: str) -> Optional[str]:
        prompt_lower = prompt.lower()
        scores = {}
        for pattern_name, matchers in self.PATTERN_MATCHERS.items():
            score = sum(1 for p in matchers if re.search(p, prompt_lower))
            if score > 0:
                scores[pattern_name] = score
        if scores:
            best = max(scores.items(), key=lambda x: x[1])
            if best[1] >= 1:
                return best[0]
        return None
    
    def _customize_code(self, code: str, intent: CrystallizedIntent, prompt: str) -> str:
        if intent.target_name:
            code = re.sub(r'\bEntity\b', intent.target_name, code)
        return code


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Qombinator - Evolutionary Synthesizer')
    parser.add_argument('--text', '-t', type=str, help='Task')
    parser.add_argument('--list', '-l', action='store_true', help='List patterns')
    args = parser.parse_args()
    if args.list:
        print("Complex Patterns:", list(Qombinator.COMPLEX_PATTERNS.keys()))
    elif args.text:
        intent = CrystallizedIntent(raw_text=args.text)
        code = Qombinator().synthesize(intent, args.text)
        print(code if code else "No pattern found")
