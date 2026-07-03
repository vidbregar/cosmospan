package latency

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"

	"github.com/vidbregar/federation-descheduler/pkg/plugins"
	v1 "k8s.io/api/core/v1"
)

type Latencies struct {
	InterCluster map[string]map[string]int            `json:"inter-cluster"` // cluster_x -> cluster_y
	IntraCluster map[string]map[string]map[string]int `json:"intra-cluster"` // cluster -> node_x -> node_y
}

type LatencyEvictor struct {
	snapshot        *State
	latencies       *Latencies
	latencyRequests map[string]map[string]int // workload_x -> workload_y -> int
}

const name = "Latency"

func (l *LatencyEvictor) Name() string {
	return name
}

func PrettyPrint(v any) {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		fmt.Printf("Error pretty-printing: %v\n", err)
		return
	}
	fmt.Println(string(b))
}

func (l *LatencyEvictor) Filter(pod *v1.Pod) bool {
	workload := pod.Labels["id"]

	//fmt.Println("workload -----")
	//PrettyPrint(workload)
	//fmt.Println("latencies -----")
	//PrettyPrint(l.latencies)
	//fmt.Println("latencyRequests -----")
	//PrettyPrint(l.latencyRequests)
	//fmt.Println("snapshot -----")
	//PrettyPrint(l.snapshot)

	currentNode := pod.Spec.NodeName
	currentCluster := l.snapshot.nodes[currentNode]

	requests, ok := l.latencyRequests[workload]
	if !ok {
		return false // no requests, nothing to check
	}

	for depWorkload, latencyReq := range requests {
		clustersMap := l.snapshot.workloads[depWorkload]

		for cluster := range clustersMap {
			if cluster == currentCluster {
				// check nodes as well
				nodesMap := clustersMap[cluster]
				for node := range nodesMap {
					if node == currentNode {
						continue
					}

					latency, ok := l.latencies.IntraCluster[cluster][min(node, currentNode)][max(node, currentNode)]
					if !ok {
						panic("")
					}
					if latency > latencyReq {
						return true
					}
				}
			} else {
				// check only cluster latencies
				latency, ok := l.latencies.InterCluster[min(cluster, currentCluster)][max(cluster, currentCluster)]
				if !ok {
					panic("")
				}
				if latency > latencyReq {
					return true
				}

			}
		}
	}

	return false
}

func New(snapshot *State) plugins.Evictor {
	log.Printf("Creating new %s plugin\n", name)

	var latencies Latencies

	latenciesFile, err := os.Open("/dataset/node-latencies.json")
	if err != nil {
		panic(err)
	}
	defer latenciesFile.Close()

	latenciesBytes, err := io.ReadAll(latenciesFile)
	if err != nil {
		panic(err)
	}

	err = json.Unmarshal(latenciesBytes, &latencies)
	if err != nil {
		panic(err)
	}

	var latencyRequests map[string]map[string]int

	latencyRequestsFile, err := os.Open("/dataset/workload-latency-requests.json")
	if err != nil {
		panic(err)
	}
	defer latencyRequestsFile.Close()

	latencyRequestsBytes, err := io.ReadAll(latencyRequestsFile)
	if err != nil {
		panic(err)
	}

	err = json.Unmarshal(latencyRequestsBytes, &latencyRequests)
	if err != nil {
		fmt.Println(err)
		panic(err)
	}

	return &LatencyEvictor{
		snapshot:        snapshot,
		latencies:       &latencies,
		latencyRequests: latencyRequests,
	}
}
