package nodes

import (
	"fmt"
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// Mirrors agent/generate_data_summary.py — pure functions, no LLM. Used by
// /query, /query/stream, /query/patch, /query/execute-sql to produce per-column
// statistics for the frontend's data preview pane and chat data context.

var (
	isoDatetimeRE = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$`)
	dateOnlyRE    = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)
)

// ComputeDataSummary builds the per-column stats payload from query rows.
// `totalRecordsAvailable` is the row count before LIMIT, when known.
func ComputeDataSummary(rows []map[string]any, totalRecordsAvailable *int) *models.DataSummary {
	if len(rows) == 0 {
		return &models.DataSummary{
			RowCount:              0,
			TotalRecordsAvailable: totalRecordsAvailable,
			ColumnCount:           0,
			Columns:               map[string]*models.ColumnSummary{},
		}
	}

	// Collect column names in insertion order from the first row.
	cols := make([]string, 0, len(rows[0]))
	for k := range rows[0] {
		cols = append(cols, k)
	}
	// Stable order for deterministic output.
	sort.Strings(cols)

	summary := &models.DataSummary{
		RowCount:              len(rows),
		TotalRecordsAvailable: totalRecordsAvailable,
		ColumnCount:           len(cols),
		Columns:               make(map[string]*models.ColumnSummary, len(cols)),
	}

	for _, col := range cols {
		all := make([]any, len(rows))
		for i, row := range rows {
			all[i] = row[col]
		}
		summary.Columns[col] = computeColumnSummary(all)
	}
	return summary
}

func computeColumnSummary(values []any) *models.ColumnSummary {
	nonNull := make([]any, 0, len(values))
	for _, v := range values {
		if v != nil {
			nonNull = append(nonNull, v)
		}
	}

	cs := &models.ColumnSummary{
		Type:          detectColumnType(nonNull),
		NullCount:     len(values) - len(nonNull),
		DistinctCount: distinctCount(nonNull),
	}

	switch cs.Type {
	case "numeric":
		applyNumericStats(cs, nonNull)
	case "text":
		applyTextStats(cs, nonNull)
	case "datetime":
		applyDatetimeStats(cs, nonNull)
	}
	return cs
}

// detectColumnType returns the dominant type across the column's non-null
// values. Order matches Python (booleans take priority over numerics; ISO
// strings are detected as datetime; numeric strings count as numeric).
func detectColumnType(values []any) string {
	if len(values) == 0 {
		return "null"
	}
	counts := map[string]int{}
	for _, v := range values {
		switch x := v.(type) {
		case bool:
			counts["boolean"]++
		case float64, float32, int, int8, int16, int32, int64, uint, uint8, uint16, uint32, uint64:
			counts["numeric"]++
		case string:
			if isoDatetimeRE.MatchString(x) || dateOnlyRE.MatchString(x) {
				counts["datetime"]++
			} else if _, err := strconv.ParseFloat(x, 64); err == nil {
				counts["numeric"]++
			} else {
				counts["text"]++
			}
		default:
			counts["text"]++
		}
	}
	// Most common wins; ties broken by Python's iteration order, which
	// happens to favor whichever was inserted first. We pick a stable order
	// over the keys to keep behavior deterministic in Go.
	type kv struct {
		k string
		v int
	}
	pairs := make([]kv, 0, len(counts))
	for k, v := range counts {
		pairs = append(pairs, kv{k, v})
	}
	sort.SliceStable(pairs, func(i, j int) bool {
		if pairs[i].v != pairs[j].v {
			return pairs[i].v > pairs[j].v
		}
		return pairs[i].k < pairs[j].k
	})
	if len(pairs) == 0 {
		return "null"
	}
	return pairs[0].k
}

func distinctCount(values []any) int {
	seen := make(map[string]struct{}, len(values))
	for _, v := range values {
		seen[fmt.Sprint(v)] = struct{}{}
	}
	return len(seen)
}

func applyNumericStats(cs *models.ColumnSummary, values []any) {
	nums := make([]float64, 0, len(values))
	for _, v := range values {
		if f, ok := toFloat(v); ok {
			nums = append(nums, f)
		}
	}
	if len(nums) == 0 {
		return
	}
	min, max := nums[0], nums[0]
	sum := 0.0
	for _, n := range nums {
		if n < min {
			min = n
		}
		if n > max {
			max = n
		}
		sum += n
	}
	avg := sum / float64(len(nums))
	med := median(nums)
	roundedAvg := round4(avg)
	roundedMed := round4(med)
	roundedSum := round4(sum)
	cs.Min = &min
	cs.Max = &max
	cs.Avg = &roundedAvg
	cs.Median = &roundedMed
	cs.Sum = &roundedSum
}

func applyTextStats(cs *models.ColumnSummary, values []any) {
	if len(values) == 0 {
		return
	}
	strs := make([]string, 0, len(values))
	for _, v := range values {
		strs = append(strs, fmt.Sprint(v))
	}
	minLen, maxLen := len(strs[0]), len(strs[0])
	totalLen := 0
	freq := make(map[string]int, len(strs))
	for _, s := range strs {
		l := len(s)
		if l < minLen {
			minLen = l
		}
		if l > maxLen {
			maxLen = l
		}
		totalLen += l
		freq[s]++
	}
	avgLen := round2(float64(totalLen) / float64(len(strs)))
	cs.MinLength = &minLen
	cs.MaxLength = &maxLen
	cs.AvgLength = &avgLen

	// Top 5 by count, ties broken alphabetically for stable output.
	type kv struct {
		v string
		n int
	}
	pairs := make([]kv, 0, len(freq))
	for v, n := range freq {
		pairs = append(pairs, kv{v, n})
	}
	sort.SliceStable(pairs, func(i, j int) bool {
		if pairs[i].n != pairs[j].n {
			return pairs[i].n > pairs[j].n
		}
		return pairs[i].v < pairs[j].v
	})
	limit := 5
	if len(pairs) < limit {
		limit = len(pairs)
	}
	cs.TopValues = make([]models.TopValueEntry, 0, limit)
	for i := 0; i < limit; i++ {
		cs.TopValues = append(cs.TopValues, models.TopValueEntry{
			Value: pairs[i].v, Count: pairs[i].n,
		})
	}
}

func applyDatetimeStats(cs *models.ColumnSummary, values []any) {
	type tsEntry struct {
		original string
		t        time.Time
	}
	parsed := make([]tsEntry, 0, len(values))
	for _, v := range values {
		s, ok := v.(string)
		if !ok {
			s = fmt.Sprint(v)
		}
		t, ok := parseAnyDatetime(s)
		if ok {
			parsed = append(parsed, tsEntry{original: s, t: t})
		}
	}
	if len(parsed) == 0 {
		return
	}
	minIdx, maxIdx := 0, 0
	for i := 1; i < len(parsed); i++ {
		if parsed[i].t.Before(parsed[minIdx].t) {
			minIdx = i
		}
		if parsed[i].t.After(parsed[maxIdx].t) {
			maxIdx = i
		}
	}
	cs.MinDatetime = parsed[minIdx].original
	cs.MaxDatetime = parsed[maxIdx].original
	rangeDays := round2(parsed[maxIdx].t.Sub(parsed[minIdx].t).Hours() / 24)
	cs.RangeDays = &rangeDays
}

// parseAnyDatetime tries each format Python's _parse_datetime supports.
// Returns the parsed time and whether parsing succeeded.
func parseAnyDatetime(s string) (time.Time, bool) {
	s = strings.TrimSuffix(s, "Z")
	formats := []string{
		"2006-01-02T15:04:05.000000",
		"2006-01-02T15:04:05",
		"2006-01-02 15:04:05.000000",
		"2006-01-02 15:04:05",
		"2006-01-02",
	}
	for _, f := range formats {
		if t, err := time.Parse(f, s); err == nil {
			return t, true
		}
	}
	return time.Time{}, false
}

func toFloat(v any) (float64, bool) {
	switch x := v.(type) {
	case float64:
		return x, true
	case float32:
		return float64(x), true
	case int:
		return float64(x), true
	case int64:
		return float64(x), true
	case int32:
		return float64(x), true
	case bool:
		// Python excludes booleans from numeric stats — mirror that.
		_ = x
		return 0, false
	case string:
		if f, err := strconv.ParseFloat(x, 64); err == nil {
			return f, true
		}
	}
	return 0, false
}

func median(nums []float64) float64 {
	cp := append([]float64(nil), nums...)
	sort.Float64s(cp)
	n := len(cp)
	if n == 0 {
		return 0
	}
	if n%2 == 1 {
		return cp[n/2]
	}
	return (cp[n/2-1] + cp[n/2]) / 2
}

func round2(f float64) float64 { return math.Round(f*100) / 100 }
func round4(f float64) float64 { return math.Round(f*10000) / 10000 }
