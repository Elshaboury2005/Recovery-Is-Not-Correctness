"""Explicit abrupt SIGKILL condition with the standard bounded hold/rollback."""
from app.reliability.fault_injectors.base_fault import register_fault_injector
from app.reliability.fault_injectors.container_stop_fault import ContainerStopFault


@register_fault_injector
class ContainerSigkillFault(ContainerStopFault):
    fault_type = "container_sigkill"
    label = "Abrupt container termination (SIGKILL)"
    description = "Immediately sends SIGKILL without a graceful shutdown period, then starts the container after the configured duration."
    blast_radius = "Interrupts in-flight work; uncommitted writes may fail or require replay."
    icon = "square"

    def inject(self, target_service: str, params: dict) -> dict:
        result = self._docker.kill_container(target_service)
        return {**result, "fault_type": self.fault_type}
