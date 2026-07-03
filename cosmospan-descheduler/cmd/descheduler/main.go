package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"path/filepath"
	"time"

	"github.com/alitto/pond"
	"github.com/vidbregar/federation-descheduler/pkg/plugins"
	"github.com/vidbregar/federation-descheduler/pkg/plugins/bandwidth"
	"github.com/vidbregar/federation-descheduler/pkg/plugins/latency"
	"github.com/vidbregar/federation-descheduler/pkg/plugins/unscheduled"
	"github.com/vidbregar/federation-descheduler/pkg/plugins/uptime"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

func recreatePod(k8sClient *kubernetes.Clientset, pod *v1.Pod) error {
	namespace := pod.Namespace

	// Delete the pod
	err := k8sClient.CoreV1().Pods(namespace).Delete(context.TODO(), pod.Name, metav1.DeleteOptions{})
	if err != nil {
		return err
	}

	// Wait for deletion (hack for simulation)
	time.Sleep(1 * time.Second)

	return nil
}

func PrettyPrint(v any) {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		fmt.Printf("Error pretty-printing: %v\n", err)
		return
	}
	fmt.Println(string(b))
}

func main() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)

	kubeconfig := filepath.Join("/etc/kubernetes/kubeconfig.yaml")
	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		config, err = rest.InClusterConfig()
		if err != nil {
			log.Fatal(err)
		}
	}

	k8sClient, err := kubernetes.NewForConfig(config)
	if err != nil {
		log.Fatal(err)
	}

	log.Println("Configured k8s client")

	// POC only, this bookkeeping would be kept in sync while the platform runs, rather than computed from scratch.
	log.Println("Starting bandwidth snapshot...")
	bandwidthsSnapshot := bandwidth.SnapshotBandwidths(k8sClient)
	log.Println("Starting workloads snapshot...")
	workloadsSnapshot := latency.SnapshotWorkloads(k8sClient)

	PrettyPrint(workloadsSnapshot)

	evictors := []plugins.Evictor{
		unscheduled.New(),
		uptime.New(k8sClient),
		bandwidth.New(bandwidthsSnapshot),
		latency.New(workloadsSnapshot),
	}

	// List pods
	pods, err := k8sClient.CoreV1().Pods(metav1.NamespaceAll).List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		panic(err.Error())
	}

	log.Println("Starting scan...")
	pool := pond.New(100, 1000)

	evicted := 0
	unscheduledPods := 0
	for _, pod := range pods.Items {
		pod := &pod
		pool.Submit(func() {
			for _, evictor := range evictors {
				if evictor.Filter(pod) {
					// log.Printf("Pod %s will be evicted by the %s evictor", pod.Name, evictor.Name())
					// POC only, in practice, PDBs should be respected
					err := recreatePod(k8sClient, pod)
					if err != nil {
						log.Println(err.Error())
					}

					if evictor.Name() == "Unscheduled" {
						unscheduledPods += 1
					}

					evicted += 1
					break
				}
			}
		})
	}

	pool.StopAndWait()

	log.Println("Scan complete")
	log.Println()
	log.Println()
	log.Println(fmt.Sprintf("Rescheduled %.2f%% of previously scheduled pods", (float64(evicted-unscheduledPods)/float64(len(pods.Items)-unscheduledPods))*100))
	log.Println()
	log.Println()
}
