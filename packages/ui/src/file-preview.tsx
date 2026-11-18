import * as React from "react";

import { Icon } from "./icons";
import { say } from "./words";

export interface FilePreviewProps {
  name: string;
  size?: number;
  columns?: string[];
  rows: string[][];
  total?: number;
  onRemove?: () => void;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FilePreview({ name, size, columns, rows, total, onRemove }: FilePreviewProps) {
  const hidden = total !== undefined ? Math.max(0, total - rows.length) : 0;
  return (
    <figure className="file-preview">
      <figcaption className="file-preview-head">
        <Icon name="clip" />
        <span className="file-preview-name">{name}</span>
        {size !== undefined && <span className="file-preview-size">{fileSize(size)}</span>}
        {onRemove && (
          <button type="button" className="file-preview-remove" aria-label={say("file_preview.remove")} onClick={onRemove}>
            <Icon name="close" />
          </button>
        )}
      </figcaption>
      {rows.length === 0 ? (
        <p className="file-preview-empty">{say("file_preview.empty")}</p>
      ) : (
        <div className="file-preview-scroll">
          <table>
            {columns && (
              <thead>
                <tr>
                  {columns.map((column, at) => (
                    <th key={at} scope="col">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {rows.map((row, at) => (
                <tr key={at}>
                  {row.map((cell, index) => (
                    <td key={index}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {hidden > 0 && <p className="file-preview-more">{say("file_preview.more", { count: hidden })}</p>}
    </figure>
  );
}
