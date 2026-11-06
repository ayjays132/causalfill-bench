# Optional isolated deployment

The Dockerfile is an example building block, not a tested deployment or a claim that containers make an evaluation secure. Docker was not used for the release measurements. Start the evaluator on a private network, pin the base image digest, mount a writable result directory owned by UID10001, provide a fresh CFB_TOKEN, and impose CPU/memory/PID/time limits. Give the agent only the small client and the private evaluator endpoint. Do not mount the benchmark source or Docker socket into the agent.

Keep the evaluator unprivileged and its root filesystem read-only when practical, with only its result volume writable. Allow the agent to contact the evaluator and its configured model provider, not unrestricted solution repositories. Record the actual network policy and image digests. Do not expose the stdlib HTTP server directly to the public internet; it is a development service without production authentication management or transport termination.

The prototype can also run without Docker for development. Such a shared-host run is appropriate for debugging and scripted controls, but cannot establish strong isolation from an agent able to inspect that host.
