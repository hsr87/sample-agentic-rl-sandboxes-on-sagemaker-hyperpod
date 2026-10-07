// agentcore-shim makes a task image satisfy the Amazon Bedrock AgentCore Runtime
// HTTP contract (listen on :8080, answer GET /ping and POST /invocations), so the
// image can serve as a Harbor sandbox. Shell commands do not pass through this
// server; they run via InvokeAgentRuntimeCommand. The shim only adds:
//
//   - health: /ping always answers "Healthy" without time_of_last_update, so an
//     abandoned session idles out instead of living (and billing) until the
//     maximum session lifetime
//   - file transfer: InvokeAgentRuntimeCommand caps a command at 64 KB, while an
//     InvokeAgentRuntime payload may be 100 MB, so files move through
//     /invocations as base64 in one call
//
// Adapted from the Harbor AgentCore shim in github.com/mightma/harbor (branch
// acr-kit-v1, commit 4ee0cb25, Apache-2.0), whose health handshake follows
// agentcore-sandboxd in github.com/awslabs/agentcore-rl-toolkit (Apache-2.0).
// Change: the "busy" state (HealthyBusy) was removed, because a client that
// never sent "stop" left the session running until maxLifetime.
package main

import (
	"encoding/base64"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

const (
	listenAddr = "0.0.0.0:8080"
	// Shim-side cap on a file read or written in one call. The end-to-end limit is lower: the request and response
	// travel base64-encoded inside InvokeAgentRuntime payloads (100,000,000 bytes), so about 75 MB of raw data.
	maxUploadBytes = 96 << 20
)

type invocation struct {
	Action string `json:"action"`
	Path   string `json:"path"`
	Data   string `json:"data"`
	Mode   uint32 `json:"mode"`
}

func writeJSON(w http.ResponseWriter, status int, body map[string]string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func fail(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"status": "error", "error": msg})
}

func handlePing(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "Healthy"})
}

// upload writes to a temp file in the target directory and renames it into place,
// so a failed transfer never leaves a truncated file behind.
func upload(req *invocation) error {
	data, err := base64.StdEncoding.DecodeString(req.Data)
	if err != nil {
		return err
	}
	if len(data) > maxUploadBytes {
		return os.ErrInvalid
	}
	dir := filepath.Dir(req.Path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, ".shim-upload-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	mode := os.FileMode(req.Mode)
	if mode == 0 {
		mode = 0o644
	}
	if err := os.Chmod(tmp.Name(), mode); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), req.Path)
}

func handleInvocations(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		fail(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	var req invocation
	if err := json.NewDecoder(io.LimitReader(r.Body, maxUploadBytes*4/3+(1<<20))).Decode(&req); err != nil {
		fail(w, http.StatusBadRequest, "malformed JSON body")
		return
	}
	switch req.Action {
	case "ping":
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	case "upload":
		if req.Path == "" {
			fail(w, http.StatusBadRequest, "upload requires a path")
			return
		}
		if err := upload(&req); err != nil {
			fail(w, http.StatusInternalServerError, "upload failed: "+err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "path": req.Path})
	case "download":
		// Refuse files that cannot fit in one response instead of reading them into memory.
		if st, err := os.Stat(req.Path); err == nil && st.Size() > maxUploadBytes {
			fail(w, http.StatusRequestEntityTooLarge, "download failed: file larger than the response limit")
			return
		}
		data, err := os.ReadFile(req.Path)
		if err != nil {
			fail(w, http.StatusNotFound, "download failed: "+err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{
			"status": "ok", "path": req.Path, "data": base64.StdEncoding.EncodeToString(data),
		})
	default:
		fail(w, http.StatusBadRequest, "unknown action: "+req.Action)
	}
}

func main() {
	// Warm-up before listening: AgentCore V2 takes the snapshot after the first healthy /ping, so whatever the
	// warm-up reads (Python, task libraries, task data) is already in memory in every restored session.
	// Bounded well below the 120 s initialization limit; a failure only costs speed.
	warmup()
	log.SetFlags(0)
	mux := http.NewServeMux()
	mux.HandleFunc("/ping", handlePing)
	mux.HandleFunc("/invocations", handleInvocations)
	log.Printf("agentcore-shim listening on %s", listenAddr)
	log.Fatal(http.ListenAndServe(listenAddr, mux))
}

const warmupScript = "/usr/local/share/harbor/warmup.sh"

func warmup() {
	if _, err := os.Stat(warmupScript); err != nil {
		return
	}
	start := time.Now()
	cmd := exec.Command("/bin/sh", warmupScript)
	if err := cmd.Start(); err != nil {
		log.Printf("warm-up not started: %v", err)
		return
	}
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case err := <-done:
		log.Printf("warm-up finished in %s (err=%v)", time.Since(start).Round(time.Millisecond), err)
	case <-time.After(90 * time.Second):
		_ = cmd.Process.Kill()
		log.Printf("warm-up stopped after 90s")
	}
}
