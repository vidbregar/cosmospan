package bandwidth

import (
	"context"
	"log"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	mapset "github.com/deckarep/golang-set/v2"
	v1 "k8s.io/api/core/v1"
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

const logLevel = 5

type Bandwidth struct {
	handle         framework.Handle
	k8sClient      *kubernetes.Clientset
	nodeCapacities map[string]*Capacity
}

var _ = framework.FilterPlugin(&Bandwidth{})
var _ = framework.ScorePlugin(&Bandwidth{})
var _ = framework.ReservePlugin(&Bandwidth{})

const Name = "Bandwidth"

func (b *Bandwidth) Name() string {
	return Name
}

func (b *Bandwidth) Filter(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeInfo *framework.NodeInfo) *framework.Status {
	const epsilon = 0.1

	// ingress
	ingressReqStr, ok := pod.Labels["ingress-bandwidth-request-Mbps"]
	if ok {
		ingressReq, err := strconv.ParseFloat(strings.TrimSpace(ingressReqStr), 64)
		if err != nil {
			klog.V(logLevel).ErrorS(err, "error converting string to float")
			return framework.NewStatus(framework.Error, "")
		}

		capacity, ok := b.nodeCapacities[nodeInfo.Node().Name]
		if !ok {
			klog.V(logLevel).Infof("node %s does not specify ingress as requested by pod %s", nodeInfo.Node().Name, pod.Name)
			return framework.NewStatus(framework.Unschedulable, "")
		}

		if ingressReq+capacity.IngressReqs > capacity.TotalIngress-epsilon {
			klog.V(logLevel).Infof("not enough free ingress on node %s for pod %s", nodeInfo.Node().Name, pod.Name)
			return framework.NewStatus(framework.Unschedulable, "")
		}
	}

	// egress
	egressReqStr, ok := pod.Labels["egress-bandwidth-request-Mbps"]
	if ok {
		egressReq, err := strconv.ParseFloat(strings.TrimSpace(egressReqStr), 64)
		if err != nil {
			klog.V(logLevel).ErrorS(err, "error converting string to float")
			return framework.NewStatus(framework.Error, "")
		}

		capacity, ok := b.nodeCapacities[nodeInfo.Node().Name]
		if !ok {
			klog.V(logLevel).Infof("node %s does not specify egress as requested by pod %s", nodeInfo.Node().Name, pod.Name)
			return framework.NewStatus(framework.Unschedulable, "")
		}

		if egressReq+capacity.EgressReqs > capacity.TotalEgress-epsilon {
			klog.V(logLevel).Infof("not enough free egress on node %s for pod %s", nodeInfo.Node().Name, pod.Name)
			return framework.NewStatus(framework.Unschedulable, "")
		}
	}

	return framework.NewStatus(framework.Success, "")
}

func (b *Bandwidth) Score(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) (int64, *framework.Status) {
	_, hasIngressRequest := pod.Labels["ingress-bandwidth-request-Mbps"]
	_, hasEgressRequest := pod.Labels["egress-bandwidth-request-Mbps"]

	if hasIngressRequest && hasEgressRequest {
		// only nodes with both ingress and egress capacities will be scored here
		// no preference, hence return the same score for all of them
		return framework.MaxNodeScore, framework.NewStatus(framework.Success)
	}

	if hasIngressRequest {
		// only nodes with both ingress and egress or only ingress capacities will be scored here
		// prefer nodes with only ingress, so that the those with both capacities can be left for other nodes
		nodeHasEgress := b.nodeCapacities[nodeName].TotalEgress > 0
		if nodeHasEgress {
			return framework.MinNodeScore, framework.NewStatus(framework.Success)
		}

		return framework.MaxNodeScore, framework.NewStatus(framework.Success)
	}

	if hasEgressRequest {
		// only nodes with both ingress and egress or only egress capacities will be scored here
		// prefer nodes with only egress, so that the those with both capacities can be left for other nodes
		nodeHasIngress := b.nodeCapacities[nodeName].TotalIngress > 0
		if nodeHasIngress {
			return framework.MinNodeScore, framework.NewStatus(framework.Success)
		}

		return framework.MaxNodeScore, framework.NewStatus(framework.Success)
	}

	// otherwise pod has no requests, prefer nodes that do not define capacities
	capacity, hasCapacity := b.nodeCapacities[nodeName]
	if !hasCapacity {
		return framework.MaxNodeScore, framework.NewStatus(framework.Success)
	}

	// if that is not possible prefer nodes with either only ingress or egress
	if capacity.TotalEgress == 0 || capacity.TotalIngress == 0 {
		return framework.MaxNodeScore / 2, framework.NewStatus(framework.Success)
	}

	// if that is not possible, schedule a pod without requests on a node with both ingress and egress capacities
	return framework.MinNodeScore, framework.NewStatus(framework.Success)
}

func (b *Bandwidth) NormalizeScore(ctx context.Context, state *framework.CycleState, p *v1.Pod, scores framework.NodeScoreList) *framework.Status {
	return framework.NewStatus(framework.Success, "")
}

func (b *Bandwidth) ScoreExtensions() framework.ScoreExtensions {
	return b
}

func (b *Bandwidth) Reserve(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) *framework.Status {
	_, ok := b.nodeCapacities[nodeName]
	if !ok {
		// nothing to reserve, node does not specify bandwidth capacities and the pod does not request them
		return framework.NewStatus(framework.Success, "")
	}

	if b.nodeCapacities[nodeName].PodUIDs.Contains(string(pod.UID)) {
		// already accounted for, idempotency
		return framework.NewStatus(framework.Success, "")
	}

	ingressReqStr, ok := pod.Labels["ingress-bandwidth-request-Mbps"]
	if ok {
		ingressReq, err := strconv.ParseFloat(strings.TrimSpace(ingressReqStr), 64)
		if err != nil {
			klog.V(logLevel).ErrorS(err, "error converting string to float")
			return framework.NewStatus(framework.Error, "")
		}

		b.nodeCapacities[nodeName].IngressReqs += ingressReq
		b.nodeCapacities[nodeName].PodUIDs.Add(string(pod.UID))
	}

	egressReqStr, ok := pod.Labels["egress-bandwidth-request-Mbps"]
	if ok {
		egressReq, err := strconv.ParseFloat(strings.TrimSpace(egressReqStr), 64)
		if err != nil {
			klog.V(logLevel).ErrorS(err, "error converting string to float")
			return framework.NewStatus(framework.Error, "")
		}

		b.nodeCapacities[nodeName].EgressReqs += egressReq
		b.nodeCapacities[nodeName].PodUIDs.Add(string(pod.UID))
	}

	return framework.NewStatus(framework.Success, "")
}

func (b *Bandwidth) Unreserve(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) {
	if !b.nodeCapacities[nodeName].PodUIDs.Contains(string(pod.UID)) {
		// not in map or already unreserved, idempotency
		return
	}

	ingressReqStr, ok := pod.Labels["ingress-bandwidth-request-Mbps"]
	if ok {
		ingressReq, err := strconv.ParseFloat(strings.TrimSpace(ingressReqStr), 64)
		if err != nil {
			klog.V(logLevel).ErrorS(err, "error converting string to float")
			return
		}

		b.nodeCapacities[nodeName].IngressReqs -= ingressReq
		b.nodeCapacities[nodeName].PodUIDs.Remove(string(pod.UID))
	}

	egressReqStr, ok := pod.Labels["egress-bandwidth-request-Mbps"]
	if ok {
		egressReq, err := strconv.ParseFloat(strings.TrimSpace(egressReqStr), 64)
		if err != nil {
			klog.V(logLevel).ErrorS(err, "error converting string to float")
			return
		}

		b.nodeCapacities[nodeName].EgressReqs -= egressReq
		b.nodeCapacities[nodeName].PodUIDs.Remove(string(pod.UID))
	}
}

type NodeWork struct {
	Event string
	Node  *v1.Node
}

type Capacity struct {
	TotalIngress float64
	TotalEgress  float64

	IngressReqs float64
	EgressReqs  float64

	PodUIDs mapset.Set[string]
}

func (b *Bandwidth) updateIngress(nodeName string, ingress float64) {
	_, exists := b.nodeCapacities[nodeName]
	if !exists {
		b.nodeCapacities[nodeName] = &Capacity{
			TotalIngress: 0,
			TotalEgress:  0,
			IngressReqs:  0,
			EgressReqs:   0,
			PodUIDs:      mapset.NewSet[string](),
		}
	}

	b.nodeCapacities[nodeName].TotalIngress = ingress
}

func (b *Bandwidth) updateEgress(nodeName string, egress float64) {
	_, exists := b.nodeCapacities[nodeName]
	if !exists {
		b.nodeCapacities[nodeName] = &Capacity{
			TotalIngress: 0,
			TotalEgress:  0,
			IngressReqs:  0,
			EgressReqs:   0,
			PodUIDs:      mapset.NewSet[string](),
		}
	}

	b.nodeCapacities[nodeName].TotalEgress = egress
}

func (b *Bandwidth) ListenNodeEvents() {
	// Create a shared informer factory
	factory := informers.NewSharedInformerFactory(b.k8sClient, 0)

	// Get an informer for nodes
	nodeInformer := factory.Core().V1().Nodes().Informer()

	// Create a queue to process events
	queue := workqueue.NewRateLimitingQueue(workqueue.DefaultControllerRateLimiter())

	// Add event handlers to the informer
	nodeInformer.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc: func(obj interface{}) {
			node := obj.(*v1.Node)
			klog.V(logLevel).Infof("Node created: %s\n", node.Name)
			queue.Add(&NodeWork{
				Event: "create",
				Node:  node,
			})
		},
		DeleteFunc: func(obj interface{}) {
			node := obj.(*v1.Node)
			klog.V(logLevel).Infof("Node deleted: %s\n", node.Name)
			queue.Add(&NodeWork{
				Event: "delete",
				Node:  node,
			})
		},
		UpdateFunc: func(_, obj interface{}) {
			node := obj.(*v1.Node)
			klog.V(logLevel).Infof("Node updated: %s\n", node.Name)
			queue.Add(&NodeWork{
				Event: "update",
				Node:  node,
			})
		},
	})

	// Start the informer
	stopCh := make(chan struct{})
	defer close(stopCh)
	go factory.Start(stopCh)

	// Wait for the caches to be synced before starting workers
	if !cache.WaitForCacheSync(stopCh, nodeInformer.HasSynced) {
		klog.V(logLevel).Infof("Timed out waiting for caches to sync")
		return
	}

	// Process items from the queue
	for {
		x, shutdown := queue.Get()
		if shutdown {
			break
		}
		work := x.(*NodeWork)

		if work.Event == "create" {
			ingressStr, ok := work.Node.Labels["example.com/ingress-bandwidth-Mbps"]
			if ok && ingressStr != "" {
				ingress, err := strconv.ParseFloat(strings.TrimSpace(ingressStr), 64)
				if err != nil {
					klog.V(logLevel).ErrorS(err, "error converting string to float")
					panic(err)
				}

				b.updateIngress(work.Node.Name, ingress)
			} else {
				b.updateIngress(work.Node.Name, 0)
				klog.V(logLevel).Infof("node %s does not specify ingress", work.Node.Name)
			}

			egressStr, ok := work.Node.Labels["example.com/egress-bandwidth-Mbps"]
			if ok && egressStr != "" {
				egress, err := strconv.ParseFloat(strings.TrimSpace(egressStr), 64)
				if err != nil {
					klog.V(logLevel).ErrorS(err, "error converting string to float")
					panic(err)
				}

				b.updateEgress(work.Node.Name, egress)
			} else {
				b.updateEgress(work.Node.Name, 0)
				klog.V(logLevel).Infof("node %s does not specify egress", work.Node.Name)
			}
		} else if work.Event == "delete" {
			delete(b.nodeCapacities, work.Node.Name)
		} else if work.Event == "update" {
			ingressStr, ok := work.Node.Labels["example.com/ingress-bandwidth-Mbps"]
			if ok && ingressStr != "" {
				ingress, err := strconv.ParseFloat(strings.TrimSpace(ingressStr), 64)
				if err != nil {
					klog.V(logLevel).ErrorS(err, "error converting string to float")
					panic(err)
				}

				b.updateIngress(work.Node.Name, ingress)
			} else {
				b.updateIngress(work.Node.Name, 0)
				klog.V(logLevel).Infof("node %s does not specify ingress", work.Node.Name)
			}

			egressStr, ok := work.Node.Labels["example.com/egress-bandwidth-Mbps"]
			if ok && egressStr != "" {
				egress, err := strconv.ParseFloat(strings.TrimSpace(egressStr), 64)
				if err != nil {
					klog.V(logLevel).ErrorS(err, "error converting string to float")
					panic(err)
				}

				b.updateEgress(work.Node.Name, egress)
			} else {
				b.updateEgress(work.Node.Name, 0)
				klog.V(logLevel).Infof("node %s does not specify egress", work.Node.Name)
			}
		}

		queue.Done(work)
	}
}

func (b *Bandwidth) ListenPodEvents() {
	// Create a shared informer factory
	factory := informers.NewSharedInformerFactory(b.k8sClient, time.Minute*10)

	// Get an informer for pods
	podsInformer := factory.Core().V1().Pods().Informer()

	// Create a queue to process events
	queue := workqueue.NewRateLimitingQueue(workqueue.DefaultControllerRateLimiter())

	// Add event handlers to the informer
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

	// Start the informer
	stopCh := make(chan struct{})
	defer close(stopCh)
	go factory.Start(stopCh)

	// Wait for the caches to be synced before starting workers
	if !cache.WaitForCacheSync(stopCh, podsInformer.HasSynced) {
		klog.V(logLevel).Infof("Timed out waiting for caches to sync")
		return
	}

	// Process items from the queue
	for {
		x, shutdown := queue.Get()
		if shutdown {
			break
		}
		pod := x.(*v1.Pod)
		if pod.Spec.NodeName == "" {
			klog.V(logLevel).Infof("pod %s was not scheduled on a node, so no need to free up node capacities", pod.Name)
			// nothing to do, pod was not scheduled on a node
			queue.Done(pod)
			continue
		}

		node := pod.Spec.NodeName

		ingressReqStr, ok := pod.Labels["ingress-bandwidth-request-Mbps"]
		if ok {
			ingressReq, err := strconv.ParseFloat(strings.TrimSpace(ingressReqStr), 64)
			if err != nil {
				klog.V(logLevel).ErrorS(err, "error converting string to float")
				panic(err)
			}

			b.nodeCapacities[node].IngressReqs -= ingressReq
		}

		egressReqStr, ok := pod.Labels["egress-bandwidth-request-Mbps"]
		if ok {
			egressReq, err := strconv.ParseFloat(strings.TrimSpace(egressReqStr), 64)
			if err != nil {
				klog.V(logLevel).ErrorS(err, "error converting string to float")
				panic(err)
			}

			b.nodeCapacities[node].EgressReqs -= egressReq
		}

		queue.Done(pod)
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

	k8sClient, err := kubernetes.NewForConfig(config)
	if err != nil {
		panic(err.Error())
	}

	b := &Bandwidth{
		handle:         h,
		k8sClient:      k8sClient,
		nodeCapacities: make(map[string]*Capacity),
	}

	klog.V(logLevel).Infof("starting node create/delete listener")
	go b.ListenNodeEvents()

	klog.V(logLevel).Infof("starting pod delete listener")
	go b.ListenPodEvents()

	return b, nil
}
