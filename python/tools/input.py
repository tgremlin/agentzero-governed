from agent import Agent, UserMessage
from python.helpers.tool import Tool, Response
from python.helpers.governance_gate import evaluate_tool_gate
from python.tools.code_execution_tool import CodeExecution


class Input(Tool):

    async def execute(self, keyboard="", **kwargs):
        # normalize keyboard input
        keyboard = keyboard.rstrip()
        # keyboard += "\n" # no need to, code_exec does that

        # terminal session number
        session = int(self.args.get("session", 0))

        # forward keyboard input to code execution tool
        args = {
            "runtime": "terminal",
            "code": keyboard,
            "session": session,
            "allow_running": True,
        }

        # === GOVERNANCE_MODE BEGIN ===
        gate = evaluate_tool_gate(self.agent, "code_execution_tool", args)
        decision = str(gate.get("decision", "allow"))
        if decision == "require_approval":
            return Response(
                message="Governance approval requested for terminal input execution.",
                break_loop=False,
                additional={
                    "approval_id": gate.get("approval_id"),
                    "risk": gate.get("risk"),
                },
            )
        if decision == "deny":
            return Response(
                message="Governance denied terminal input execution.",
                break_loop=False,
                additional={"risk": gate.get("risk")},
            )

        args["__governance_gate_evaluated"] = gate.get("token", "")
        args["__governance_tool_call_hash"] = gate.get("tool_call_hash", "")
        # === GOVERNANCE_MODE END ===

        cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message, self.loop_data)
        cet.log = self.log
        return await cet.execute(**args)

    def get_log_object(self):
        return self.agent.context.log.log(type="code_exe", heading=f"icon://keyboard {self.agent.agent_name}: Using tool '{self.name}'", content="", kvps=self.args)

    async def after_execution(self, response, **kwargs):
        self.agent.hist_add_tool_result(self.name, response.message, **(response.additional or {}))
