import { useParams } from "react-router-dom";
import { useRecordMedia, useReprocessMedia, useReviewMedia } from "@/hooks/useRecords";
import { useAuth } from "@/context/AuthContext";
import Icon from "@/components/ui/Icon";
import ErrorState from "@/components/ui/ErrorState";
import type { RecordMedia } from "@/types";
import { formatDate } from "@/lib/format";

// Media gallery: content is visible while classification remains explicit
// through persistent badges and review controls.

export default function RecordMediaTab() {
  const { id = "" } = useParams();
  const media = useRecordMedia(id);
  const review = useReviewMedia(id);
  const reprocess = useReprocessMedia(id);
  const { user } = useAuth();
  const canReview = user?.role === "admin" || user?.role === "operator";

  if (media.isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-64 bg-surface-container-low rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }
  if (media.isError) {
    return <ErrorState error={media.error} onRetry={() => media.refetch()} />;
  }
  if (!media.data || media.data.length === 0) {
    return <p className="text-body-md text-on-surface-variant">Nessun media associato a questo record.</p>;
  }

  return (
    <div>
      <h3 className="text-headline-sm text-on-surface mb-4">Media Assets ({media.data.length})</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {media.data.map((item) => (
          <MediaCard
            key={item.id}
            item={item}
            canReview={canReview}
            onReview={(classification) => {
              const notes = window.prompt("Note di revisione (obbligatorie):");
              if (notes?.trim()) review.mutate({ mediaId: item.id, classification, notes: notes.trim() });
            }}
            onReprocess={() => reprocess.mutate(item.id)}
          />
        ))}
      </div>
    </div>
  );
}

function MediaCard({
  item,
  canReview,
  onReview,
  onReprocess,
}: {
  item: RecordMedia;
  canReview: boolean;
  onReview: (classification: "safe" | "explicit") => void;
  onReprocess: () => void;
}) {
  return (
    <div className="bg-surface-container-lowest border border-border rounded-lg overflow-hidden flex flex-col">
      <div className="relative h-48 bg-surface-container-low w-full overflow-hidden">
        <img
          src={item.thumbnailUrl}
          alt=""
          className="w-full h-full object-cover"
        />
        <div className="absolute top-2 right-2 bg-surface-container-lowest/90 rounded-full px-2 py-1 flex items-center gap-1 border border-border/50">
          <Icon name={item.type === "video" ? "movie" : "image"} size={16} className="text-info" />
          <span className="text-label-sm text-on-surface">{item.type === "video" ? "VID" : "IMG"}</span>
        </div>
      </div>
      <div className="p-4 flex-1 flex flex-col justify-between">
        <div>
          <div className="flex justify-between items-start mb-2">
            <span
              className={
                item.sensitivity === "explicit"
                  ? "shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-label-sm bg-error/10 text-error border border-error/20"
                  : "shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-label-sm bg-success/10 text-success border border-success/20"
              }
            >
              {item.sensitivity === "explicit" ? "Esplicito" : "Sicuro"}
            </span>
            {item.reviewStatus === "required" && (
              <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-label-sm bg-warning/10 text-warning border border-warning/20">
                Da revisionare
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-label-sm text-on-surface-variant mb-4">
            <Icon name="language" size={14} />
            <span>Fonte: {item.sourceName}</span>
            <span className="text-border">&bull;</span>
            <span>{formatDate(item.addedAt)}</span>
          </div>
        </div>
        <div className="flex justify-between border-t border-border pt-3 mt-auto">
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="text-label-sm text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1"
          >
            <Icon name="open_in_new" size={16} />
            Visualizza
          </a>
          {canReview && item.reviewStatus === "required" && (
            <div className="flex gap-2">
              <button type="button" onClick={() => onReview("safe")} className="text-label-sm text-success">Segna come sicuro</button>
              <button type="button" onClick={() => onReview("explicit")} className="text-label-sm text-error">Segna come esplicito</button>
            </div>
          )}
          {canReview && item.processingStatus === "failed" && (
            <button type="button" onClick={onReprocess} className="text-label-sm text-primary">Rielabora</button>
          )}
        </div>
      </div>
    </div>
  );
}
