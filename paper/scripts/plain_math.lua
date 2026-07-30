local replacements = {
  ["C"] = "C",
  ["\\mathcal{G}=(V,E,\\tau_V,\\tau_E)"] = "𝒢 = (V, E, τ_V, τ_E)",
  ["q"] = "q",
  ["R_C(q)=(c_1,c_2,\\ldots), \\qquad c_i\\in C."] = "R_C(q) = (c_1, c_2, …),  c_i ∈ C.",
  ["C_q^*"] = "C_q*",
  ["P_G(q)=\\{p_1,p_2,\\ldots\\}, \\qquad p_i=(v_1,e_1,v_2,\\ldots,v_k),"] = "P_G(q) = {p_1, p_2, …},  p_i = (v_1, e_1, v_2, …, v_k),",
  ["K"] = "K",
  ["k_1=1.2"] = "k1 = 1.2",
  ["b=0.75"] = "b = 0.75",
  ["c"] = "c",
  ["s_{\\mathrm{RRF}}(c)=\\sum_{r\\in\\{b,t,g\\}}\\frac{w_r}{k_0+\\operatorname{rank}_r(c)},"] = "s_RRF(c) = Σ[r ∈ {b, t, g}] w_r / (k_0 + rank_r(c)),",
  ["k_0=60"] = "k_0 = 60",
  ["w_b=w_t=1"] = "w_b = w_t = 1",
  ["w_g=0.5"] = "w_g = 0.5",
  ["s(c)=\\frac{1}{60+r_{\\mathrm{BM25}}(c)}+\\frac{1}{60+r_{\\mathrm{dense}}(c)}+\\frac{0.25I_{\\mathrm{table}}(c)}{61}."] = "s(c) = 1/(60 + r_BM25(c)) + 1/(60 + r_dense(c)) + 0.25 I_table(c)/61.",
  ["\\kappa"] = "κ",
  ["p=0.024"] = "p = 0.024",
  ["\\kappa=0.792"] = "κ = 0.792",
  ["=0.918"] = " = 0.918",
  ["n=30"] = "n = 30",
  ["^{*}"] = "*"
}

function Math(element)
  local replacement = replacements[element.text]
  if replacement == nil then
    io.stderr:write("Unmapped LaTeX math expression: " .. element.text .. "\n")
    replacement = element.text
      :gsub("\\ldots", "…")
      :gsub("\\kappa", "κ")
      :gsub("\\in", "∈")
      :gsub("[{}]", "")
  end
  return pandoc.Str(replacement)
end
