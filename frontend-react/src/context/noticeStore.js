import { createContext, useContext } from "react";

export const NoticeContext = createContext({
  notify: () => null,
  dismiss: () => {},
});

export function useNotice() {
  return useContext(NoticeContext);
}
