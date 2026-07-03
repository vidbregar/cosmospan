package latency

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	mapset "github.com/deckarep/golang-set/v2"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/informers"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/cache"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/workqueue"
	"k8s.io/klog/v2"
	"k8s.io/kubernetes/pkg/scheduler/framework"
)

type Latency struct {
	handle          framework.Handle
	k8sClient       *kubernetes.Clientset
	latencies       *Latencies
	latencyRequests map[string]map[string]int                  // workload_x -> workload_y -> int
	workloads       map[string]map[string]map[string]*Replicas // workload -> cluster -> node -> replica_count
}

type Replicas struct {
	Count int
	Names mapset.Set[string]
}

type Latencies struct {
	InterCluster map[string]map[string]int            `json:"inter-cluster"` // cluster_x -> cluster_y
	IntraCluster map[string]map[string]map[string]int `json:"intra-cluster"` // cluster -> node_x -> node_y
}

var _ = framework.PreFilterPlugin(&Latency{})
var _ = framework.FilterPlugin(&Latency{})
var _ = framework.ScorePlugin(&Latency{})
var _ = framework.ReservePlugin(&Latency{})

const Name = "Latency"

const logLevel = 5

func (l *Latency) Name() string {
	return Name
}

// keep a structure in memory where for each workload is a map to clusters where it is deployed.
// Each cluster is also a map to nodes where it is deployed. Each node is a key with a value representing replicas of that workload on the node.
// This structure is updated in postBind (incrementing value) and on pod delete events (decrementing value)

// verify this again
// m = max # of nodes in a cluster
// w = # of workloads
// c = # of clusters
// n = total # of nodes
//
// n(w*c + w*m)
//
// n*w*m if sequential, but n is run in parallel, so only w*m

func (l *Latency) PreFilter(ctx context.Context, state *framework.CycleState, pod *v1.Pod) (*framework.PreFilterResult, *framework.Status) {
	return nil, framework.NewStatus(framework.Success)
}

func (l *Latency) PreFilterExtensions() framework.PreFilterExtensions {
	return nil
}

func (l *Latency) Filter(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeInfo *framework.NodeInfo) *framework.Status {
	workload := pod.Labels["id"]

	nodeConsidered := nodeInfo.Node().Name
	clusterConsidered := getNodeCluster(nodeInfo.Node())

	requests, ok := l.latencyRequests[workload]
	if !ok {
		klog.V(logLevel).Infof("pod %s of workload %s does not have any latency requests", pod.Name, workload)
		return framework.NewStatus(framework.Success)
	}

	for depWorkload, latencyReq := range requests {
		clustersMap := l.workloads[depWorkload]

		klog.V(logLevel).Infof("verifying dep workload %s for pod %s on potential node %s", depWorkload, pod.Name, nodeConsidered)
		for cluster := range clustersMap {
			if cluster == clusterConsidered {
				// check nodes as well
				nodesMap := clustersMap[cluster]
				for node := range nodesMap {
					if node == nodeConsidered {
						continue
					}

					latency, ok := l.latencies.IntraCluster[cluster][min(node, nodeConsidered)][max(node, nodeConsidered)]
					if !ok {
						panic(fmt.Sprintf("no intra cluster latency found for %s and %s", min(node, nodeConsidered), max(node, nodeConsidered)))
					}
					if node != nodeConsidered && latency > latencyReq {
						klog.V(logLevel).Infof("requested latency %d, but in cluster: %s node %s to node: %s is %d", latencyReq, cluster, node, nodeConsidered, latency)
						return framework.NewStatus(framework.Unschedulable)
					}

					klog.V(logLevel).Infof("requested latency %d and node: %s to node: %s is %d, OK!", latencyReq, nodeConsidered, node, latency)
				}
			} else {
				// check only cluster latencies
				latency, ok := l.latencies.InterCluster[min(cluster, clusterConsidered)][max(cluster, clusterConsidered)]
				if !ok {
					panic(fmt.Sprintf("no inter cluster latency found for %s and %s", min(cluster, clusterConsidered), max(cluster, clusterConsidered)))
				}
				if latency > latencyReq {
					klog.V(logLevel).Infof("requested latency %d, but cluster: %s to cluster: %s is %d", latencyReq, clusterConsidered, cluster, latency)
					return framework.NewStatus(framework.Unschedulable)
				}
				klog.V(logLevel).Infof("requested latency %d and cluster: %s to cluster: %s is %d, OK!", latencyReq, clusterConsidered, cluster, latency)
			}
		}
	}

	klog.V(logLevel).Infof("node %s passed all check for pod %s of worklaod %s", nodeConsidered, pod.Name, workload)

	return framework.NewStatus(framework.Success, "")
}

func getNodeCluster(node *v1.Node) string {
	cluster := node.Labels["topology.kubernetes.io/region"]
	if cluster == "" {
		klog.V(logLevel).ErrorS(errors.New(fmt.Sprintf("no cluster has been identified for node %s", node.Name)), "")
		panic("")
	}

	return cluster
}

func (l *Latency) Score(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) (int64, *framework.Status) {
	// no preferences here
	return framework.MaxNodeScore, framework.NewStatus(framework.Success)
}

func (l *Latency) NormalizeScore(ctx context.Context, state *framework.CycleState, p *v1.Pod, scores framework.NodeScoreList) *framework.Status {
	return framework.NewStatus(framework.Success, "")
}

func (l *Latency) ScoreExtensions() framework.ScoreExtensions {
	return l
}

func (l *Latency) Reserve(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) *framework.Status {
	// update a map tracking in which clusters and on which nodes workload replicas run. Increment by 1

	workload := pod.Labels["id"] // test data puts workload id here, alternatively we would find the parent deployment

	nodeInfo, err := l.handle.SnapshotSharedLister().NodeInfos().Get(nodeName)
	if err != nil {
		klog.V(logLevel).ErrorS(err, "Unable to get node info")
		panic("")
	}

	node := nodeInfo.Node()
	cluster := getNodeCluster(node)

	if l.workloads[workload] == nil {
		l.workloads[workload] = make(map[string]map[string]*Replicas)
	}

	if l.workloads[workload][cluster] == nil {
		l.workloads[workload][cluster] = make(map[string]*Replicas)
	}

	if l.workloads[workload][cluster][node.Name] == nil {
		l.workloads[workload][cluster][node.Name] = &Replicas{
			Count: 0,
			Names: mapset.NewSet[string](),
		}
	}

	if !l.workloads[workload][cluster][node.Name].Names.Contains(pod.Name) {
		l.workloads[workload][cluster][node.Name].Count += 1
		l.workloads[workload][cluster][node.Name].Names.Add(pod.Name)
	}

	return framework.NewStatus(framework.Success, "")
}

func (l *Latency) Unreserve(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) {
	workload := pod.Labels["id"]

	nodeInfo, err := l.handle.SnapshotSharedLister().NodeInfos().Get(nodeName)
	if err != nil {
		klog.V(logLevel).ErrorS(err, "Unable to get node info")
		panic("")
	}

	node := nodeInfo.Node()
	cluster := getNodeCluster(node)

	if l.workloads[workload][cluster][nodeName].Names.Contains(pod.Name) {
		l.workloads[workload][cluster][nodeName].Count -= 1
		l.workloads[workload][cluster][nodeName].Names.Remove(pod.Name)

		if l.workloads[workload][cluster][nodeName].Count <= 0 {
			delete(l.workloads[workload][cluster], nodeName)
		}

		if len(l.workloads[workload][cluster]) == 0 {
			delete(l.workloads[workload], cluster)
		}

		if len(l.workloads[workload]) == 0 {
			delete(l.workloads, workload)
		}
	}
}

func (l *Latency) ListenPodEvents() {
	// Create a shared informer factory
	factory := informers.NewSharedInformerFactory(l.k8sClient, time.Minute*10)

	podsInformer := factory.Core().V1().Pods().Informer()

	queue := workqueue.NewRateLimitingQueue(workqueue.DefaultControllerRateLimiter())

	podsInformer.AddEventHandler(cache.ResourceEventHandlerFuncs{
		DeleteFunc: func(obj interface{}) {
			if obj == nil {
				return
			}

			pod := obj.(*v1.Pod)
			klog.V(logLevel).Infof("Pod deleted: %s\n", pod.Name)
			queue.Add(pod)
		},
	})

	stopCh := make(chan struct{})
	defer close(stopCh)
	go factory.Start(stopCh)

	if !cache.WaitForCacheSync(stopCh, podsInformer.HasSynced) {
		klog.V(logLevel).Infof("Timed out waiting for caches to sync")
		return
	}

	for {
		x, shutdown := queue.Get()
		if shutdown {
			break
		}
		pod := x.(*v1.Pod)

		workload := pod.Labels["id"]

		if pod.Spec.NodeName == "" {
			// probably delete event of unscheduled pod
			queue.Done(pod)
			continue
		}

		node, err := l.k8sClient.CoreV1().Nodes().Get(context.TODO(), pod.Spec.NodeName, metav1.GetOptions{})
		if err != nil {
			panic(err.Error())
		}

		cluster := getNodeCluster(node)
		nodeName := node.Name

		if _, ok := l.workloads[workload]; !ok {
			queue.Done(pod)
			continue
		}

		if _, ok := l.workloads[workload][cluster]; !ok {
			queue.Done(pod)
			continue
		}

		if _, ok := l.workloads[workload][nodeName]; !ok {
			queue.Done(pod)
			continue
		}

		if l.workloads[workload][cluster][nodeName].Names.Contains(pod.Name) {
			l.workloads[workload][cluster][nodeName].Count -= 1
			l.workloads[workload][cluster][nodeName].Names.Remove(pod.Name)

			if l.workloads[workload][cluster][nodeName].Count <= 0 {
				delete(l.workloads[workload][cluster], nodeName)
			}

			if len(l.workloads[workload][cluster]) == 0 {
				delete(l.workloads[workload], cluster)
			}

			if len(l.workloads[workload]) == 0 {
				delete(l.workloads, workload)
			}
		}

		queue.Done(pod)
	}
}

func PrintJSON(obj interface{}) {
	bytes, _ := json.MarshalIndent(obj, "\t", "\t")
	fmt.Println(string(bytes))
}

func (l *Latency) refreshLatencies() {
	var latencies Latencies

	latenciesFile, err := os.Open("/etc/federation-scheduler/node-latencies.json")
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
	//old := l.latencies
	l.latencies = &latencies

	//fmt.Println(cmp.Diff(old, l.latencies))
}

func (l *Latency) listenRefresh() {
	http.HandleFunc("/refresh", func(writer http.ResponseWriter, request *http.Request) {
		l.refreshLatencies()
		writer.WriteHeader(200)
	})

	port := ":8888"
	fmt.Printf("Server is listening on port %s\n", port)
	err := http.ListenAndServe(port, nil) // Start the server
	if err != nil {
		fmt.Printf("Error starting server: %s\n", err)
	}
}

func New(ctx context.Context, args runtime.Object, h framework.Handle) (framework.Plugin, error) {
	klog.V(logLevel).Infof("creating new Bandwidth plugin")

	kubeconfig := filepath.Join("/etc/kubernetes/kubeconfig.yaml")
	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		config, err = rest.InClusterConfig()
		if err != nil {
			log.Fatal(err)
		}
	}

	var latencies Latencies

	latenciesFile, err := os.Open("/etc/federation-scheduler/node-latencies.json")
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

	latencyRequestsFile, err := os.Open("/etc/federation-scheduler/workload-latency-requests.json")
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

	k8sClient, err := kubernetes.NewForConfig(config)
	if err != nil {
		panic(err.Error())
	}

	l := &Latency{
		handle:          h,
		k8sClient:       k8sClient,
		workloads:       make(map[string]map[string]map[string]*Replicas),
		latencies:       &latencies,
		latencyRequests: latencyRequests,
	}

	go l.listenRefresh()

	klog.V(logLevel).Infof("starting pod delete listener")
	go l.ListenPodEvents()

	return l, nil
}
