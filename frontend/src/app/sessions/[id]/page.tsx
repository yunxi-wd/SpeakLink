/** Server route resolves recording identity and mounts the client workspace. */
import Workspace from '@/components/Workspace';
/** Render the requested recording; missing IDs are handled by the API boundary. */
export default async function SessionPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <Workspace id={id} />; }
