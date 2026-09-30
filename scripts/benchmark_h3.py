"""Measure an explicitly provisioned, authorized H3 session. Does not allocate a GPU.

UGC_BENCHMARK_URL and UGC_BENCHMARK_TOKEN identify the worker. Results contain
actual observed timings, never extrapolated hardware rankings or quality claims.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import time
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=Path)
    parser.add_argument("--end", type=Path)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--seconds", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def image(path):
        if not path:
            return None
        mime = {".png":"png", ".jpg":"jpeg", ".jpeg":"jpeg", ".webp":"webp"}[path.suffix.lower()]
        return f"data:image/{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    with httpx.Client(base_url=os.environ["UGC_BENCHMARK_URL"],
                      headers={"X-Access-Token":os.environ["UGC_BENCHMARK_TOKEN"]}, timeout=30) as client:
        ready=client.get("/readiness")
        ready.raise_for_status()
        began=time.monotonic()
        response=client.post("/api/jobs-json",json={"owner":"benchmark", "renderer":"h3-fl2va",
            "prompt":args.prompt, "duration":args.seconds, "variations":args.count,
            "start_frame_data_url":image(args.start), "end_frame_data_url":image(args.end)})
        response.raise_for_status()
        ids=set(response.json()["job_ids"])
        deadline=time.monotonic()+7200
        try:
            while time.monotonic()<deadline:
                response=client.get("/api/jobs")
                response.raise_for_status()
                jobs=[j for j in response.json()["jobs"] if j["id"] in ids]
                if len(jobs)==len(ids) and all(j["status"] in {"complete","failed","cancelled"} for j in jobs):
                    elapsed=time.monotonic()-began
                    count=sum(j["status"]=="complete" for j in jobs)
                    metrics=client.get("/api/metrics")
                    metrics.raise_for_status()
                    args.output.parent.mkdir(parents=True,exist_ok=True)
                    args.output.write_text(json.dumps({"jobs":jobs,"batch_wall_seconds":elapsed,
                        "batch_successful_clips_per_hour":count/elapsed*3600,"session":metrics.json(),
                        "startup":ready.json(), "human_quality_rating":None},indent=2))
                    return
                time.sleep(2)
            raise TimeoutError("Benchmark timed out; session guardian must finish shutdown")
        finally:
            # Guardian archives all completed results and verifies termination independently.
            response=client.post("/api/session/end")
            response.raise_for_status()


if __name__ == "__main__":
    main()
