// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Browsersicht (noVNC) für Captcha und Zwei-Faktor.

export function BrowsersichtSeite({ ohneTitel = false }: { ohneTitel?: boolean }) {
  return (
    <div className={ohneTitel ? '' : 'mx-auto max-w-5xl'}>
      {!ohneTitel && <h1 className="seite-titel mb-2">Browsersicht</h1>}
      <p className="seite-beschrieb mb-4">
        Der Browser, in dem der Bot arbeitet. Hier lässt sich ein Captcha oder eine
        Bestätigung von Hand lösen, wenn ein Lauf darauf wartet.
      </p>
      {/* Eigenes Fenster statt eingebettet: Ein Captcha in einem kleinen
          Rahmen ist mühsam, und noVNC braucht die volle Tastatur. */}
      <a
        href="/browsersicht/vnc.html?autoconnect=1&resize=scale"
        target="_blank"
        rel="noreferrer"
        className="btn-primaer"
      >
        In neuem Fenster öffnen
      </a>
      <div className="karte mt-6 overflow-hidden bg-black">
        <iframe
          title="Browsersicht"
          src="/browsersicht/vnc.html?autoconnect=1&resize=scale"
          className="h-[60vh] w-full"
        />
      </div>
    </div>
  );
}
