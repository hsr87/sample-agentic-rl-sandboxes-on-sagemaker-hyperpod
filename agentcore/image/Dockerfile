# AgentCore variant of the task image: the shared base image (arm64) plus the contract shim.
# AgentCore Runtime (microVM) accepts linux/arm64 images only.
ARG BASE_IMAGE
FROM --platform=linux/arm64 golang:1.25-bookworm@sha256:3b4a11519ad929d1e1d261a12cff056f0c85b735253d7d861346b9c6f8b36437 AS shim
WORKDIR /src
COPY shim/main.go .
RUN go mod init agentcore-shim && CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -trimpath -ldflags="-s -w" -o /agentcore-shim .

FROM --platform=linux/arm64 ${BASE_IMAGE}
COPY --from=shim /agentcore-shim /usr/local/bin/agentcore-shim
# Shared sandbox warm-up (tasks/image/warmup.sh), run by the shim before the snapshot.
COPY warmup.sh /usr/local/share/harbor/warmup.sh
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/agentcore-shim"]
