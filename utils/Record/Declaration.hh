#pragma once

#include "Record/Writer.hh"

namespace Record {

template <typename Basis>
inline void Writer::declareParticleGroup(Basis basis,
                              std::string directoryName,
                              std::string displayName) {
        requireEnumBasis<Basis>();
        requireOpenForDeclaration("particle group");
        requireNotStarted("particle group");
        if (directoryName.empty())
            throw std::runtime_error("[Record::Writer] particle group directory name must not be empty");

        const RecordKey key = keyOf(basis);
        if (particleObjects_.count(key))
            throw std::runtime_error("[Record::Writer] duplicate particle group " + keyString(key));

        outFile_->cd();
        TDirectory* dir = outFile_->mkdir(directoryName.c_str());
        if (dir == nullptr)
            throw std::runtime_error("[Record::Writer] failed to create directory '" + directoryName + "'");

        ParticleObjects object{};
        object.basis = key;
        object.name  = std::move(displayName);
        object.dir   = dir;
        particleObjects_.emplace(key, std::move(object));
    }

template <typename Basis>
inline void Writer::declareParticleCount(Basis basis,
                              std::string histName,
                              std::string title,
                              int bins,
                              double low,
                              double high) {
        ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle count");
        validateHistogramShape(histName, bins, low, high);
        if (object.count.hist != nullptr)
            throw std::runtime_error("[Record::Writer] duplicate particle count for " +
                                     keyString(keyOf(basis)));

        object.dir->cd();
        object.count.hist = new TH1D(histName.c_str(), title.c_str(), bins, low, high);
    }

template <typename Basis>
inline void Writer::declareParticleHist1D(Basis basis,
                               Physics::ParticleProperty property,
                               std::string histName,
                               std::string title,
                               int bins,
                               double low,
                               double high) {
        ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle hist1D");
        validateHistogramShape(histName, bins, low, high);
        ensureUniqueParticleName(object, histName);
        object.dir->cd();
        ParticleTH1 rec{};
        rec.hist = new TH1D(histName.c_str(), title.c_str(), bins, low, high);
        rec.property = property;
        object.hists1D.push_back(std::move(rec));
    }

template <typename Basis>
inline void Writer::declareParticleHist2D(Basis basis,
                               Physics::ParticleProperty propertyX,
                               Physics::ParticleProperty propertyY,
                               std::string histName,
                               std::string title,
                               int binsX,
                               double lowX,
                               double highX,
                               int binsY,
                               double lowY,
                               double highY) {
        ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle hist2D");
        validateHistogramShape(histName, binsX, lowX, highX);
        validateHistogramShape(histName, binsY, lowY, highY);
        ensureUniqueParticleName(object, histName);
        object.dir->cd();
        ParticleTH2 rec{};
        rec.hist = new TH2D(histName.c_str(), title.c_str(),
                            binsX, lowX, highX, binsY, lowY, highY);
        rec.propertyX = propertyX;
        rec.propertyY = propertyY;
        object.hists2D.push_back(std::move(rec));
    }

template <typename Basis>
inline void Writer::declareParticleGraph(Basis basis,
                              Physics::ParticleProperty propertyX,
                              Physics::ParticleProperty propertyY,
                              std::string graphName,
                              std::string title) {
        ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle graph");
        validateObjectName(graphName, "particle graph");
        ensureUniqueParticleName(object, graphName);
        object.dir->cd();
        auto* graph = new TGraph();
        graph->SetName(graphName.c_str());
        graph->SetTitle(title.c_str());
        ParticleGraph rec{};
        rec.graph = graph;
        rec.propertyX = propertyX;
        rec.propertyY = propertyY;
        object.graphs.push_back(std::move(rec));
    }

template <typename Basis>
inline void Writer::declareParticleProfile(Basis basis,
                                Physics::ParticleProperty propertyX,
                                Physics::ParticleProperty propertyY,
                                std::string profileName,
                                std::string title,
                                int binsX,
                                double lowX,
                                double highX) {
        ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle profile");
        validateHistogramShape(profileName, binsX, lowX, highX);
        ensureUniqueParticleName(object, profileName);
        object.dir->cd();
        ParticleProfile rec{};
        rec.profile = new TProfile(profileName.c_str(), title.c_str(), binsX, lowX, highX);
        rec.propertyX = propertyX;
        rec.propertyY = propertyY;
        object.profiles.push_back(std::move(rec));
    }

template <typename Basis>
inline void Writer::declareParticleTree(Basis basis,
                             std::string treeName,
                             std::string title,
                             std::vector<Physics::ParticleProperty> properties) {
        ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle tree");
        validateObjectName(treeName, "particle tree");
        if (object.tree.tree != nullptr)
            throw std::runtime_error("[Record::Writer] duplicate particle tree for " +
                                     keyString(keyOf(basis)));
        if (properties.empty())
            throw std::runtime_error("[Record::Writer] particle tree '" + treeName +
                                     "' must have at least one branch");

        object.dir->cd();
        object.tree.tree = new TTree(treeName.c_str(), title.c_str());
        object.tree.properties = std::move(properties);
        object.tree.branches.reserve(object.tree.properties.size());
        for (Physics::ParticleProperty property : object.tree.properties) {
            BranchRecord branch{};
            branch.name = Physics::particlePropertyName(property);
            branch.type = DataType::Double;
            branch.buffer = makeBranchBuffer(branch.type);
            declareBranch(*object.tree.tree, branch);
            object.tree.branches.push_back(std::move(branch));
        }
    }

template <typename Basis>
inline void Writer::declareHist1D(Basis basis,
                       std::string histName,
                       std::string title,
                       int bins,
                       double low,
                       double high,
                       DataType type) {
        requireEnumBasis<Basis>();
        requireOpenForDeclaration("hist1D");
        requireNotStarted("hist1D");
        validateHistogramShape(histName, bins, low, high);
        requireNumeric(type, "hist1D");
        const RecordKey key = keyOf(basis);
        if (hists1D_.count(key))
            throw std::runtime_error("[Record::Writer] duplicate hist1D " + keyString(key));
        outFile_->cd();
        Hist1DRecord rec{};
        rec.hist = new TH1D(histName.c_str(), title.c_str(), bins, low, high);
        rec.type = type;
        hists1D_.emplace(key, std::move(rec));
    }

template <typename Basis>
inline void Writer::declareHist2D(Basis basis,
                       std::string histName,
                       std::string title,
                       int binsX,
                       double lowX,
                       double highX,
                       int binsY,
                       double lowY,
                       double highY,
                       DataType typeX,
                       DataType typeY) {
        requireEnumBasis<Basis>();
        requireOpenForDeclaration("hist2D");
        requireNotStarted("hist2D");
        validateHistogramShape(histName, binsX, lowX, highX);
        validateHistogramShape(histName, binsY, lowY, highY);
        requireNumeric(typeX, "hist2D x");
        requireNumeric(typeY, "hist2D y");
        const RecordKey key = keyOf(basis);
        if (hists2D_.count(key))
            throw std::runtime_error("[Record::Writer] duplicate hist2D " + keyString(key));
        outFile_->cd();
        Hist2DRecord rec{};
        rec.hist = new TH2D(histName.c_str(), title.c_str(),
                            binsX, lowX, highX, binsY, lowY, highY);
        rec.typeX = typeX;
        rec.typeY = typeY;
        hists2D_.emplace(key, std::move(rec));
    }

template <typename Basis>
inline void Writer::declareGraph(Basis basis,
                      std::string graphName,
                      std::string title,
                      DataType typeX,
                      DataType typeY) {
        requireEnumBasis<Basis>();
        requireOpenForDeclaration("graph");
        requireNotStarted("graph");
        validateObjectName(graphName, "graph");
        requireNumeric(typeX, "graph x");
        requireNumeric(typeY, "graph y");
        const RecordKey key = keyOf(basis);
        if (graphs_.count(key))
            throw std::runtime_error("[Record::Writer] duplicate graph " + keyString(key));
        outFile_->cd();
        auto* graph = new TGraph();
        graph->SetName(graphName.c_str());
        graph->SetTitle(title.c_str());
        GraphRecord rec{};
        rec.graph = graph;
        rec.typeX = typeX;
        rec.typeY = typeY;
        graphs_.emplace(key, std::move(rec));
    }

template <typename Basis>
inline void Writer::declareProfile(Basis basis,
                        std::string profileName,
                        std::string title,
                        int binsX,
                        double lowX,
                        double highX,
                        DataType typeX,
                        DataType typeY) {
        requireEnumBasis<Basis>();
        requireOpenForDeclaration("profile");
        requireNotStarted("profile");
        validateHistogramShape(profileName, binsX, lowX, highX);
        requireNumeric(typeX, "profile x");
        requireNumeric(typeY, "profile y");
        const RecordKey key = keyOf(basis);
        if (profiles_.count(key))
            throw std::runtime_error("[Record::Writer] duplicate profile " + keyString(key));
        outFile_->cd();
        ProfileRecord rec{};
        rec.profile = new TProfile(profileName.c_str(), title.c_str(), binsX, lowX, highX);
        rec.typeX = typeX;
        rec.typeY = typeY;
        profiles_.emplace(key, std::move(rec));
    }

template <typename TreeBasis, typename BranchBasis>
inline void Writer::declareTree(TreeBasis treeBasis,
                     std::string treeName,
                     std::string title,
                     std::vector<std::tuple<BranchBasis, std::string, DataType>> branches) {
        requireEnumBasis<TreeBasis>();
        requireEnumBasis<BranchBasis>();
        requireOpenForDeclaration("tree");
        requireNotStarted("tree");
        validateObjectName(treeName, "tree");
        if (branches.empty())
            throw std::runtime_error("[Record::Writer] tree '" + treeName + "' must have at least one branch");

        const RecordKey treeKey = keyOf(treeBasis);
        if (trees_.count(treeKey))
            throw std::runtime_error("[Record::Writer] duplicate tree " + keyString(treeKey));

        outFile_->cd();
        ExplicitTreeRecord treeRecord{};
        treeRecord.tree = new TTree(treeName.c_str(), title.c_str());

        for (const auto& [branchBasis, branchName, branchType] : branches) {
            validateObjectName(branchName, "tree branch");
            if (branchType == DataType::Other)
                throw std::runtime_error("[Record::Writer] unsupported branch type for '" + branchName + "'");

            const RecordKey branchKey = keyOf(branchBasis);
            if (treeRecord.branches.count(branchKey))
                throw std::runtime_error("[Record::Writer] duplicate branch key " + keyString(branchKey));

            BranchRecord branch{};
            branch.name = branchName;
            branch.type = branchType;
            branch.buffer = makeBranchBuffer(branch.type);
            declareBranch(*treeRecord.tree, branch);
            treeRecord.branchOrder.push_back(branchKey);
            treeRecord.branches.emplace(branchKey, std::move(branch));
        }

        trees_.emplace(treeKey, std::move(treeRecord));
    }

template <typename Basis>
inline void Writer::requireEnumBasis() {
        static_assert(std::is_enum_v<Basis>, "Record::Writer basis parameters must be enum types");
    }

template <typename Basis>
inline ParticleObjects& Writer::requireParticleGroupForDeclaration(Basis basis, const std::string& kind) {
        requireEnumBasis<Basis>();
        requireOpenForDeclaration(kind);
        requireNotStarted(kind);
        const RecordKey key = keyOf(basis);
        auto it = particleObjects_.find(key);
        if (it == particleObjects_.end())
            throw std::runtime_error("[Record::Writer] missing particle group for " + kind +
                                     " " + keyString(key));
        return it->second;
    }

inline void Writer::validateObjectName(const std::string& name, const std::string& kind) {
        if (name.empty())
            throw std::runtime_error("[Record::Writer] " + kind + " name must not be empty");
    }

inline void Writer::validateHistogramShape(const std::string& name, int bins, double low, double high) {
        validateObjectName(name, "histogram");
        if (bins <= 0 || !(high > low))
            throw std::runtime_error("[Record::Writer] invalid histogram shape for '" + name + "'");
    }

inline void Writer::requireNumeric(DataType type, const std::string& context) {
        if (type == DataType::String || type == DataType::Other)
            throw std::runtime_error("[Record::Writer] " + context + " requires numeric type, got " +
                                     RootUtil::typeName(type));
    }

inline void Writer::ensureUniqueParticleName(const ParticleObjects& object, const std::string& name) {
        if (object.count.hist && name == object.count.hist->GetName())
            throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
        for (const auto& record : object.hists1D)
            if (record.hist && name == record.hist->GetName())
                throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
        for (const auto& record : object.hists2D)
            if (record.hist && name == record.hist->GetName())
                throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
        for (const auto& record : object.graphs)
            if (record.graph && name == record.graph->GetName())
                throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
        for (const auto& record : object.profiles)
            if (record.profile && name == record.profile->GetName())
                throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
        if (object.tree.tree && name == object.tree.tree->GetName())
            throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
    }

} // namespace Record
