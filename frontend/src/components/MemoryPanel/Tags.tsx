// File: frontend/src/components/MemoryPanel/Tags.tsx

type Props = {
  tags: string[]
  onToggle: (tag: string) => void
}

export default function Tags({ tags, onToggle }: Props) {
  return (
    <div className="flex flex-wrap gap-1 text-xs mt-1">
      {tags.map(tag => (
        <span
          key={tag}
          className="cursor-pointer bg-blue-100 text-blue-800 px-2 py-0.5 rounded hover:bg-blue-200"
          onClick={() => onToggle(tag)}
        >
          {tag}
        </span>
      ))}
    </div>
  )
}
