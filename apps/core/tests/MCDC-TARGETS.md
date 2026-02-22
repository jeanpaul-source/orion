# MC/DC Testing Targets for orion-core

**Generated:** 2025-11-22

## Compound Conditions Found

### main.py

```python
4:The unified AI entity for homelab management.
52:    """Application lifespan handler."""
122:    description="Unified AI Entity for Homelab Management",
246:    if isinstance(vector_count, (int, float)) and vector_count > 0:
248:    elif isinstance(vector_count, str) and vector_count.strip():
265:            if gpu_temp and gpu_temp < 80
309:    if memory_data:
690:        if hasattr(route, "path") and hasattr(route, "name"):
```

### request_queue.py

```python
63:        if self.started_at and self.completed_at:
162:            session_id: Session identifier (for rate limiting)
```

### router.py

```python
35:    Uses vLLM to classify intent and route accordingly:
117:                if intent == "knowledge" and config.enable_knowledge:
130:                elif intent == "action" and config.enable_action:
145:                elif intent == "learning" and config.enable_learning:
158:                elif intent == "watch" and config.enable_watch:
337:            if intent == "knowledge" and config.enable_knowledge:
338:                # Check if subsystem supports streaming
339:                if hasattr(self.knowledge, "handle_streaming"):
354:            elif intent == "action" and config.enable_action:
361:            elif intent == "learning" and config.enable_learning:
367:            elif intent == "watch" and config.enable_watch:
469:        system_prompt = """You are an intent classifier for ORION, an AI homelab assistant.
471:Classify the user's message into one of these categories:
527:            logger.error(f"Intent classification error: {e}")
533:        Fallback intent classification using keywords.
672:            if vector_count and vector_count > 0:
```

### config.py

```python
200:        if self.data_dir == Path("/data") and not self.data_dir.exists():
```

### subsystems/knowledge.py

```python
244:        if stats and stats.get("vector_count", 0) > 0:
426:                        else "Qdrant collection empty" if vector_count <= 0 else None
```

### subsystems/action.py

```python
36:    from devia.grounded_memory import AntiDriftMemory
65:    - "Check if PostgreSQL is running and show connection count"
114:            # Initialize anti-drift memory for agentic loop
115:            memory = AntiDriftMemory()
246:            if not step_result.success and step_result.step.error:
307:        if not self.devops_available or not self.agent:
```

### subsystems/watch.py

```python
223:            True if alert was found and resolved
262:            if alert.status == AlertStatus.RESOLVED and alert.resolved_at:
315:        if enable_background_monitoring:
385:        if unhealthy_services or active_critical_alerts:
537:        if not fallback_result.get("error") and primary_result.get("error"):
629:            if memory.percent > self.thresholds["memory_percent"]:
672:                        if memory.percent < self.thresholds["memory_percent"]
718:            if not lines or not lines[0]:
763:            if memory_percent > self.thresholds["gpu_memory_percent"]:
825:        if temperature > 90 or memory_percent > 95:
873:        if "resources" in status and "error" not in status["resources"]:
881:            if "memory" in res:
1005:        if self._monitoring_task:
```

### subsystems/learning.py

```python
216:        if error:
364:        if request.papers_found or request.docs_found:
434:            True if request was found and updated
462:            True if request was found and updated
```

### **init**.py

```python
4:The unified AI entity for homelab management.
```

### debug_tracker.py

```python
182:        Calculate state diff between current and N steps back.
188:            StateDiff object or None if insufficient history
209:            if before_state[key] != after_state[key]:
244:        # Calculate state diff if we have history
285:            if previous.confidence >= 0.8 and current.confidence < 0.7:
296:            if "risky" in current.metadata or "uncertain" in current.metadata:
334:        if "Connection" in error_type or "Network" in error_type:
343:        if "Permission" in error_type or "Denied" in error_type:
346:                    "action": "Verify permissions and authentication",
352:        if "Timeout" in error_type:
362:        if trail and trail[-1].confidence < 0.7:
```

### tracing.py

```python
117:    if span and span.is_recording():
```

### integrations/telegram_bot.py

```python
7:- Push notifications for alerts
113:        """Check if user is authorized."""
121:        if not self._check_authorization(user_id):
164:        if not self._check_authorization(update.effective_user.id):
182:            "✅ Push notifications for critical events\n"
196:        if not self._check_authorization(update.effective_user.id):
230:        if not self._check_authorization(update.effective_user.id):
292:        if not self._check_authorization(update.effective_user.id):
332:        if not self._check_authorization(update.effective_user.id):
335:        if not self.alerts_history:
359:        if not self._check_authorization(query.from_user.id):
405:        if not self._check_authorization(update.effective_user.id):
438:        if "memory" in resources:
464:                f"Attempted to send notification to unauthorized user: {user_id}"
```
