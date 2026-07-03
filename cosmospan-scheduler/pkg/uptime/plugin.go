package uptime

import (
	"context"
	"fmt"
	"k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/klog/v2"
	"k8s.io/kubernetes/pkg/scheduler/framework"
	"math"
	apiconfig "sigs.k8s.io/scheduler-plugins/apis/config"
	"sigs.k8s.io/scheduler-plugins/apis/config/validation"
	"strconv"
	"strings"
)

type Uptime struct {
	handle framework.Handle
}

var _ = framework.FilterPlugin(&Uptime{})
var _ = framework.ScorePlugin(&Uptime{})

const Name = "Uptime"

func (u *Uptime) Name() string {
	return Name
}

func (u *Uptime) Filter(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeInfo *framework.NodeInfo) *framework.Status {
	klog.V(5).Infof("running filter for pod %s and node %s", pod.Name, nodeInfo.Node().Name)

	uptimeReqStr, ok := pod.Labels["uptime-30d-percentage-request"]
	if !ok {
		klog.V(5).Infof("running filter for pod %s does not specify uptime req", pod.Name)
		return framework.NewStatus(framework.Success, "")
	}

	uptimeReq, err := strconv.ParseFloat(strings.TrimSpace(uptimeReqStr), 64)
	if err != nil {
		klog.V(5).ErrorS(err, "error converting string to float")
		return framework.NewStatus(framework.Error, "")
	}

	nodeUptimeStr, ok := nodeInfo.Node().Labels["example.com/node-30d-uptime-percentage"]
	if !ok {
		klog.V(5).Infof("node %s does not specify uptime", nodeInfo.Node().Name)
		return framework.NewStatus(framework.Unschedulable, "")
	}

	nodeUptime, err := strconv.ParseFloat(strings.TrimSpace(nodeUptimeStr), 64)
	if err != nil {
		klog.V(5).ErrorS(err, "error converting string to float")
		return framework.NewStatus(framework.Error, "")
	}

	if uptimeReq > nodeUptime {
		klog.V(5).Infof("unscheduleable because %s request: %f > node request: %f", pod.Name, uptimeReq, nodeUptime)
		return framework.NewStatus(framework.Unschedulable, "")
	}

	klog.V(5).Infof("node %s passed filter stage for pod %s", nodeInfo.Node().Name, pod.Name)

	return framework.NewStatus(framework.Success, "")
}

func (u *Uptime) Score(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) (int64, *framework.Status) {
	uptimeReqStr, ok := pod.Labels["uptime-30d-percentage-request"]
	if !ok {
		return framework.MaxNodeScore, framework.NewStatus(framework.Success, "no uptime request specified")
	}

	uptimeReq, err := strconv.ParseFloat(strings.TrimSpace(uptimeReqStr), 64)
	if err != nil {
		return framework.MinNodeScore, framework.NewStatus(framework.Error, fmt.Errorf("error converting uptimeReq string to float: %w", err).Error())
	}

	nodeInfo, err := u.handle.SnapshotSharedLister().NodeInfos().Get(nodeName)
	if err != nil {
		return framework.MinNodeScore, framework.NewStatus(framework.Error, "node must specify uptime as per the filter stage")
	}

	nodeUptimeStr, ok := nodeInfo.Node().Labels["example.com/node-30d-uptime-percentage"]
	if !ok {
		return framework.MinNodeScore, framework.NewStatus(framework.Error, fmt.Errorf("error converting nodeUptimeStr string to float: %w", err).Error())
	}

	nodeUptime, err := strconv.ParseFloat(strings.TrimSpace(nodeUptimeStr), 64)
	if err != nil {
		return framework.MinNodeScore, framework.NewStatus(framework.Error, fmt.Errorf("error converting string to float: %w", err).Error())
	}

	// multiplied by 100 to increase resolution of int
	score := int64((100 - (nodeUptime - uptimeReq)) * 100)

	return score, framework.NewStatus(framework.Success)
}

func getMinMaxScores(scores framework.NodeScoreList) (int64, int64) {
	var max int64 = math.MinInt64
	var min int64 = math.MaxInt64

	for _, nodeScore := range scores {
		if nodeScore.Score > max {
			max = nodeScore.Score
		}
		if nodeScore.Score < min {
			min = nodeScore.Score
		}
	}

	return min, max
}

func (u *Uptime) NormalizeScore(ctx context.Context, state *framework.CycleState, p *v1.Pod, scores framework.NodeScoreList) *framework.Status {
	minScore, maxScore := getMinMaxScores(scores)

	allEqual := minScore == maxScore
	if allEqual {
		for i := range scores {
			scores[i].Score = framework.MaxNodeScore
		}
		return framework.NewStatus(framework.Success, "all scores were the same, setting them to max node score")
	}

	for i := range scores {
		normScore := float64(framework.MaxNodeScore) * float64(scores[i].Score-minScore) / float64(maxScore-minScore)
		scores[i].Score = int64(normScore)
	}

	return framework.NewStatus(framework.Success, "normalized scores")
}

func (u *Uptime) ScoreExtensions() framework.ScoreExtensions {
	return u
}

// New initializes a new plugin and returns it.
func New(ctx context.Context, args runtime.Object, h framework.Handle) (framework.Plugin, error) {
	klog.V(5).Infof("creating new Uptime plugin")

	wamArgs, ok := args.(*apiconfig.UptimeArgs)
	if !ok {
		return nil, fmt.Errorf("want args to be of type Uptime, got %T", args)
	}

	klog.V(5).Infof("ptime plugin arguments valid")

	if err := validation.ValidateUptimePluginArgs(wamArgs); err != nil {
		return nil, err
	}

	return &Uptime{handle: h}, nil
}
