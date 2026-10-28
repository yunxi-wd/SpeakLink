/** Ephemeral selection only; database snapshot remains authoritative. */
import { create } from 'zustand';
interface State { selectedEntity: string | null; selectedCard: string | null; pathIds: string[]; selectEntity: (id: string | null) => void; selectCard: (id: string | null) => void; setPaths: (ids: string[]) => void; reset: () => void }
export const useStore = create<State>((set) => ({ selectedEntity: null, selectedCard: null, pathIds: [], selectEntity: id => set({ selectedEntity: id, selectedCard: null }), selectCard: id => set({ selectedCard: id, selectedEntity: null }), setPaths: ids => set({ pathIds: ids }), reset: () => set({ selectedEntity: null, selectedCard: null, pathIds: [] }) }));
