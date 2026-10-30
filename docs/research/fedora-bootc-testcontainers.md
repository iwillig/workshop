# Fedora, bootc and Testcontainers

## Summary

Testcontainers can start a disposable Fedora container with a read-only root filesystem. This is useful for testing an agent's commands against Fedora userspace. It is **not a booted Fedora Atomic or bootc operating system**: the container uses the container host's kernel and does not exercise bootc installation, reboot, update or rollback.

For an actual image-based Fedora OS, build or obtain a bootc-compatible image, turn it into a bootable disk image, and boot that image in a VM. Testcontainers can help test container images or orchestrate auxiliary services, but it does not by itself boot or manage that OS as a VM. Use a separate VM lifecycle tool for boot tests. This is a research recommendation, not an implemented workshop feature.

## Reddit source limitation

The requested [Reddit discussion](https://www.reddit.com/r/Fedora/comments/1sgeg2m/fedora_atomic_bootc_migration_setup_a_new_flow/) was blocked by Reddit's network security page, including in the browser. Its post and comments could not be reviewed, so this note does not attribute any claims or migration steps to it. The conclusions below come from primary sources and a local experiment instead.

## What bootc adds

Bootc uses OCI container images to deliver transactional, in-place operating system updates. A bootc image includes a kernel; when deployed to a machine or VM, that kernel boots and the base userspace is not ordinarily running as an application container ([bootc introduction](https://bootc.dev/bootc/)).

The same image can be run by a container runtime, but that mode uses the container host's kernel rather than the image's kernel. Bootc's documentation also distinguishes build-time mutable image files from the read-only-by-default image files of a deployed system ([bootc documentation, container runtime versus bootc runtime](https://bootc.dev/bootc/print.html#container-runtime-vs-bootc-runtime)). A deployed system is not wholly immutable: the image, local configuration and persistent data have different roles ([bootc filesystem](https://bootc.dev/bootc/print.html#handling-read-only-vs-writable-locations)).

A read-only Docker root filesystem is therefore a useful **constraint for a container**, not proof that bootc's update or rollback semantics are working. Conversely, using a bootc-compatible image with Testcontainers does not cause it to boot.

## Local feasibility check

On this Apple silicon Mac, Docker reports an OrbStack Linux host with ``aarch64`` architecture. With the workshop's Testcontainers 4.15.0, a ``fedora:43`` container started successfully with network disabled, a read-only root, dropped capabilities and a writable, size-limited ``/tmp``. The container reported ``Fedora Linux 43 (Container Image)`` and ``aarch64``. A separate check as container root could not create a file in ``/usr`` because the filesystem was read-only; writing to ``/tmp`` succeeded.

The test used the image digest ``fedora@sha256:a651ddf48ea28a06ed4e1e6519f51c9f47e7a5a138722ade87369b8fbb7e5b42``. It demonstrates a Fedora container, not Fedora bootc. It does not test agent execution, complete isolation, artifact extraction or boot behavior. The workshop's [container example](../mini-agent-sandbox.rst) shows the Testcontainers controls used here; the image and commands differ.

## Options for the workshop

| Goal | Approach | What it proves | What it does not prove |
| --- | --- | --- | --- |
| Run an agent in Fedora userspace | A pinned Fedora OCI image under Testcontainers, with read-only root and an ephemeral workspace. | Commands can run against the selected userspace with the chosen container restrictions. | Fedora's own kernel, bootc deployment, OS updates or rollback. |
| Test the contents of a bootc image | Run a bootc-compatible OCI image as a container and inspect files or run userspace tests. | Image contents and selected programs behave in container mode. | The image boots or updates as an OS. |
| Test an immutable OS lifecycle | Build a bootable disk image from a bootc image and run a disposable VM. Testcontainers can run supporting services separately. | Subject to implementation, a test can exercise boot, deployment and rollback. | Security isolation without additional threat modeling and verification. |

The bootc project describes [bootable images and their deployment model](https://bootc.dev/bootc/), and [bootc-image-builder](https://github.com/osbuild/bootc-image-builder) points to the upstream image-builder implementation for generating OS artifacts. A concrete Fedora image, image-builder procedure, VM configuration and update source still need to be selected and tested for Apple silicon. Do not assume that every image or artifact supports `aarch64`.

## Suggested next experiment

Start with the Fedora container if the goal is a repeatable agent workspace. Build a reviewed image with the tools needed by Common, pin its digest, and copy a disposable source snapshot into a writable workspace. Run with no host checkout, credentials or Docker socket mounted; keep networking disabled unless a specific need is approved. Capture a patch before removing the container and review it outside the sandbox. Test timeout enforcement, output limits, cleanup, and restrictions independently ([Docker security](https://docs.docker.com/engine/security/)).

If the goal is to evaluate bootc itself, use a separate disposable VM experiment: choose an `aarch64` bootc base and supported disk-image workflow, boot a baseline, publish a changed image to a controlled registry, then verify update, reboot and rollback. Treat this as a proposed plan, not a verified procedure. Never test migration or installation against the host disk.

## Security and trade-offs

A read-only root helps constrain changes to the container filesystem, while writable mounts, temporary filesystems and any exported artifacts remain mutable. It is not an isolation guarantee. Docker containers share the Linux kernel of their container host; on this machine that is OrbStack's Linux environment, not a Fedora kernel. Container configuration, daemon access, mounts, resources and kernel vulnerabilities remain relevant ([Docker Engine security](https://docs.docker.com/engine/security/)).

A dedicated VM provides a separate guest kernel and is a better fit for OS lifecycle tests, at the cost of more setup and resource use. VM isolation also depends on configuration and the virtualization stack; it is not an unconditional security guarantee. For hostile agent code, select the boundary using a threat model rather than treating either Fedora immutability or Testcontainers as a sandbox by itself.
