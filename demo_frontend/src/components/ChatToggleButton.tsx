import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatToggleButtonProps {
  onClick: () => void;
}

export function ChatToggleButton({ onClick }: ChatToggleButtonProps) {
  return (
    <Button
      variant="default"
      size="icon-lg"
      className="fixed right-6 bottom-6 z-50 rounded-full shadow-lg"
      onClick={onClick}
    >
      <MessageSquare className="size-5" />
    </Button>
  );
}
