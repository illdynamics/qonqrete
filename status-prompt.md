ok I want you now to change the action_status messages.

change this:
action_status=Reading task
to:
action_status=Preparing

change this:
action_status=Reading clarified task
to:
action_status=Planning

change this:
action_status=Reading briQs
to:
action_status=Building

change this:
action_status: Reviewing the Qode
to:
action_status: Reviewing

make these action_status messages also show on the Action field on the webinterface and in the top right on the TUI like the old ones do now as well.

also I see this error when the inspeQtor phase is running:

agent.call.startedrole=inspeqtor model=deepseek-v4-flash
18:31:21agent.output.startedrole=inspeqtor
18:31:21review.per_group_errorgroup_id=bg-header group_name=Header & Navigation error=inspeqtor: agent did not write 'inspeqtor_output.json' (exit_code=1). stderr: [c
18:31:21agent.call.failedrole=inspeqtor
18:31:21agent.call.startedrole=inspeqtor model=deepseek-v4-flash
18:31:21agent.output.startedrole=inspeqtor
18:31:21review.per_group_errorgroup_id=bg-scaffold group_name=Project Scaffolding & Config error=inspeqtor: agent did not write 'inspeqtor_output.json' (exit_code=1). stderr: [c
18:31:21agent.call.failedrole=inspeqtor
18:31:21agent.call.startedrole=inspeqtor model=deepseek-v4-flash
18:31:21agent.output.startedrole=inspeqtor
18:31:21review.per_group_errorgroup_id=bg-about group_name=About Page error=inspeqtor: agent did not write 'inspeqtor_output.json' (exit_code=1). stderr: [c
18:32:24agent.call.finishedrole=inspeqtor model=deepseek-v4-flash ex

can you find the cause and fix that as well and tell me how you fixed it and what the root cause was?
