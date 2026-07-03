package nodecost

import (
	"context"
	"fmt"
	"k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/klog/v2"
	"k8s.io/kubernetes/pkg/scheduler/framework"
	"math"
	"strconv"
	"strings"
)

type NodeCost struct {
	handle framework.Handle
}

var _ = framework.ScorePlugin(&NodeCost{})

const Name = "NodeCost"

func (nc *NodeCost) Name() string {
	return Name
}

func (nc *NodeCost) Score(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) (int64, *framework.Status) {
	nodeInfo, err := nc.handle.SnapshotSharedLister().NodeInfos().Get(nodeName)
	if err != nil {
		return framework.MinNodeScore, framework.NewStatus(framework.Error, "Cannot get node info")
	}

	nodeCostStr, ok := nodeInfo.Node().Labels["example.com/node-cost"]
	if !ok {
		return framework.MinNodeScore, framework.NewStatus(framework.Error, "Did not specify required example.com/node-cost")
	}

	nodeCost, err := strconv.ParseFloat(strings.TrimSpace(nodeCostStr), 64)
	if err != nil {
		return framework.MinNodeScore, framework.NewStatus(framework.Error, fmt.Errorf("error converting string to float: %w", err).Error())
	}

	return int64(nodeCost), framework.NewStatus(framework.Success)
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

func (nc *NodeCost) NormalizeScore(ctx context.Context, state *framework.CycleState, p *v1.Pod, scores framework.NodeScoreList) *framework.Status {
	minScore, maxScore := getMinMaxScores(scores)

	allEqual := minScore == maxScore
	if allEqual {
		for i := range scores {
			scores[i].Score = framework.MaxNodeScore
		}
		return framework.NewStatus(framework.Success, "all scores were the same, setting them to max node score")
	}

	for i := range scores {
		normScore := float64(framework.MaxNodeScore) * (1 - float64(scores[i].Score-minScore)/float64(maxScore-minScore))
		scores[i].Score = int64(normScore)
	}

	return framework.NewStatus(framework.Success, "normalized scores")
}

func (nc *NodeCost) ScoreExtensions() framework.ScoreExtensions {
	return nc
}

func New(ctx context.Context, args runtime.Object, h framework.Handle) (framework.Plugin, error) {
	klog.V(5).Infof("creating new NodeCost plugin")

	return &NodeCost{handle: h}, nil
}
