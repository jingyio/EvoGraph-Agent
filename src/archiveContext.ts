import { createContext, useContext } from "react";
export const ArchiveExperimentContext = createContext("");
export const useArchiveExperiment = () => useContext(ArchiveExperimentContext);
