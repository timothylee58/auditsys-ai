import { Button } from "@/components/ui/button";

export function ReviewActions() {
  return (
    <div className="flex gap-2">
      <Button type="button">Approve</Button>
      <Button type="button" variant="secondary">
        Escalate
      </Button>
    </div>
  );
}
