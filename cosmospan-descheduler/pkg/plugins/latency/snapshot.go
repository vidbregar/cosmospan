package latency

import (
	"context"
	"fmt"
	"log"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

type State struct {
	workloads map[string]map[string]map[string]bool // workload -> clusters -> nodes
	nodes     map[string]string                     // node_name -> cluster
}

func getNodeCluster(node *v1.Node) string {
	return node.Labels["topology.kubernetes.io/region"]
}

func printProgressBar(iteration, total int, barLength int) {
	percent := float64(iteration) / float64(total)
	filledLength := int(float64(barLength) * percent)

	bar := ""
	for i := 0; i < filledLength; i++ {
		bar += "="
	}
	for i := filledLength; i < barLength; i++ {
		bar += " "
	}

	fmt.Printf("\r[%s] %.2f%%", bar, percent*100)
}

func SnapshotWorkloads(k8sClient *kubernetes.Clientset) *State {
	// workload -> clusters -> nodes
	workloadsSnapshot := make(map[string]map[string]map[string]bool)
	nodesSnapshot := make(map[string]string)

	nodes, err := k8sClient.CoreV1().Nodes().List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		log.Fatalf("Error listing nodes: %s", err.Error())
	}

	total := len(nodes.Items)
	for i, node := range nodes.Items {
		printProgressBar(i, total, 50)

		nodeName := node.Name
		cluster := getNodeCluster(&node)
		nodesSnapshot[nodeName] = cluster

		pods, err := k8sClient.CoreV1().Pods("").List(context.TODO(), metav1.ListOptions{
			FieldSelector: fmt.Sprintf("spec.nodeName=%s", nodeName),
		})
		if err != nil {
			log.Fatalf("Error listing pods for node %s: %s", nodeName, err.Error())
		}

		for _, pod := range pods.Items {
			workload := pod.Labels["id"]

			_, ok := workloadsSnapshot[workload]
			if !ok {
				workloadsSnapshot[workload] = make(map[string]map[string]bool)
			}

			_, ok = workloadsSnapshot[workload][cluster]
			if !ok {
				workloadsSnapshot[workload][cluster] = make(map[string]bool)
			}

			workloadsSnapshot[workload][cluster][nodeName] = true
		}
	}

	return &State{
		workloads: workloadsSnapshot,
		nodes:     nodesSnapshot,
	}
}
