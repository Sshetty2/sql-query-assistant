import { useState, useRef, useEffect, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  TooltipProvider,
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { SAMPLE_QUESTIONS, type QuestionCategory } from "@/data/sampleQuestions";

interface QueryInputProps {
  onSubmit: (prompt: string) => void;
  disabled?: boolean;
  activeDbId?: string | null;
}

function CategoryCard({
  category,
  isActive,
  onMouseEnter,
}: {
  category: QuestionCategory;
  isActive: boolean;
  onMouseEnter: () => void;
}) {
  return (
    <button
      type="button"
      onMouseEnter={onMouseEnter}
      className={cn(
        "inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all duration-200 cursor-default select-none",
        isActive
          ? "border-primary/50 bg-primary/5 text-foreground shadow-sm"
          : "border-border text-muted-foreground hover:text-foreground hover:border-primary/30"
      )}
    >
      <span className="text-sm leading-none">{category.icon}</span>
      <span className="font-medium">{category.label}</span>
    </button>
  );
}

function QuestionBubble({
  text,
  index,
  onClick,
}: {
  text: string;
  index: number;
  onClick: (text: string) => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            onClick={() => onClick(text)}
            style={{ animationDelay: `${index * 50}ms` }}
            className="animate-in fade-in-0 slide-in-from-bottom-1 fill-mode-both inline-flex items-center text-xs px-3 py-1.5 rounded-full border border-border text-muted-foreground hover:text-foreground hover:border-primary/50 hover:bg-primary/5 transition-colors max-w-[260px] cursor-pointer"
          >
            <span className="truncate">{text}</span>
          </button>
        }
      />
      <TooltipContent side="top">{text}</TooltipContent>
    </Tooltip>
  );
}

export function QueryInput({
  onSubmit,
  disabled,
  activeDbId,
}: QueryInputProps) {
  const [prompt, setPrompt] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [isTouchDevice, setIsTouchDevice] = useState(false);
  const leaveTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  // Key to force re-mount of question bubbles for stagger animation replay
  const [animKey, setAnimKey] = useState(0);

  const categories = activeDbId ? SAMPLE_QUESTIONS[activeDbId] ?? [] : [];
  const activeQuestions =
    categories.find((c) => c.label === activeCategory)?.questions ?? [];

  useEffect(() => {
    setIsTouchDevice(window.matchMedia("(pointer: coarse)").matches);
  }, []);

  useEffect(() => {
    return () => clearTimeout(leaveTimeoutRef.current);
  }, []);

  // Reset active category when database changes
  useEffect(() => {
    setActiveCategory(null);
  }, [activeDbId]);

  const handleCategoryEnter = (label: string) => {
    clearTimeout(leaveTimeoutRef.current);
    if (label !== activeCategory) {
      setActiveCategory(label);
      setAnimKey((k) => k + 1);
    }
  };

  const handleAreaLeave = () => {
    leaveTimeoutRef.current = setTimeout(() => setActiveCategory(null), 300);
  };

  const handleAreaEnter = () => {
    clearTimeout(leaveTimeoutRef.current);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleQuestionClick = (text: string) => setPrompt(text);

  return (
    <div className="space-y-2">
      <form onSubmit={handleSubmit} className="flex gap-3 items-end">
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your data..."
          disabled={disabled}
          className="min-h-[60px] resize-none flex-1"
          rows={2}
        />
        <Button
          type="submit"
          disabled={disabled || !prompt.trim()}
          className="h-[60px] px-6"
        >
          {disabled ? "Running..." : "Query"}
        </Button>
      </form>

      {categories.length > 0 && !disabled && (
        <TooltipProvider delay={400} closeDelay={0}>
          <div
            onMouseEnter={handleAreaEnter}
            onMouseLeave={handleAreaLeave}
            className="space-y-2"
          >
            {/* Category cards */}
            <div className="flex flex-wrap gap-2">
              {categories.map((cat) => (
                <CategoryCard
                  key={cat.label}
                  category={cat}
                  isActive={activeCategory === cat.label}
                  onMouseEnter={() => handleCategoryEnter(cat.label)}
                />
              ))}
            </div>

            {/* Questions for the active category */}
            <div
              className={cn(
                "overflow-hidden transition-all duration-250 ease-out",
                activeQuestions.length > 0
                  ? "max-h-40 opacity-100"
                  : "max-h-0 opacity-0"
              )}
            >
              <div key={animKey} className="flex flex-wrap gap-2 pt-1">
                {activeQuestions.map((q, i) => (
                  <QuestionBubble
                    key={q}
                    text={q}
                    index={i}
                    onClick={handleQuestionClick}
                  />
                ))}
              </div>
            </div>

            {/* Touch fallback: show all questions flat */}
            {isTouchDevice && !activeCategory && (
              <div className="flex flex-wrap gap-2">
                {categories.flatMap((cat) =>
                  cat.questions.slice(0, 2).map((q) => (
                    <QuestionBubble
                      key={q}
                      text={q}
                      index={0}
                      onClick={handleQuestionClick}
                    />
                  ))
                )}
              </div>
            )}
          </div>
        </TooltipProvider>
      )}
    </div>
  );
}
